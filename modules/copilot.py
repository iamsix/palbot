import aiohttp
import asyncio
import base64
import io
import json
import re
import time
from datetime import datetime
from discord.ext import commands
import discord
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
from modules.ai_cache import (AICache, SETTINGS_SPEC, SETTINGS_HELP,
                              GLOBAL_SETTINGS, SECRET_SETTINGS)
from modules.llm_providers import CopilotProvider, OpenAIProvider
from modules.context_gatherer import ContextGatherer

BOT_ADMIN_ROLE = "Bot Admin"

def is_bot_admin():
    """Check: bot owner OR has the Bot Admin role."""
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        return any(role.name == BOT_ADMIN_ROLE for role in ctx.author.roles)
    return commands.check(predicate)

async def _check_bot_admin(ctx) -> bool:
    """Inline check: bot owner OR has the Bot Admin role."""
    if await ctx.bot.is_owner(ctx.author):
        return True
    return any(role.name == BOT_ADMIN_ROLE for role in ctx.author.roles)


class Copilot(commands.Cog):
    DISCORD_EPOCH = 1420070400000  # Jan 1, 2015 in ms

    def __init__(self, bot):
        self.bot = bot
        self.ai_cache = AICache()
        self.provider = CopilotProvider(bot)
        self.glm_provider = OpenAIProvider(bot)
        self.context_gatherer = ContextGatherer(bot, self.ai_cache, self.provider)

    def cog_unload(self):
        asyncio.ensure_future(self.ai_cache.close())

    async def get_provider_auth(self):
        """Get authentication from provider.

        Returns tuple of (token, base_url) or raises on failure.
        """
        return await self.provider.get_auth()

    IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    IMAGE_URL_PATTERN = re.compile(r'https?://\S+', re.IGNORECASE)
    MAX_IMAGE_BYTES = 3_500_000  # ~3.5MB raw; base64 is ~33% larger → ~4.7MB (API limit ~5MB)
    MAX_IMAGE_DIMENSION = 2048   # max width or height in pixels

    @staticmethod
    def _downscale_image(data: bytes, max_bytes: int, max_dim: int) -> tuple[bytes, str]:
        """Downscale image if too large. Returns (bytes, mime_type).

        Converts to JPEG for efficiency. Progressively reduces size until
        it fits within max_bytes.
        """
        img = Image.open(io.BytesIO(data))

        # Convert to RGB (handles RGBA PNGs, palette images, etc.)
        if img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Downscale if dimensions exceed max
        w, h = img.size
        if w > max_dim or h > max_dim:
            ratio = min(max_dim / w, max_dim / h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

        # Encode as JPEG, reduce quality until it fits
        for quality in (85, 70, 50, 30):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            result = buf.getvalue()
            if len(result) <= max_bytes:
                return result, "image/jpeg"

        # Last resort: shrink dimensions further
        w, h = img.size
        for scale in (0.5, 0.25):
            small = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            buf = io.BytesIO()
            small.save(buf, format="JPEG", quality=50, optimize=True)
            result = buf.getvalue()
            if len(result) <= max_bytes:
                return result, "image/jpeg"

        # Give up and return whatever we have
        return result, "image/jpeg"

    async def _download_url(self, url: str, probe: bool = False) -> tuple[bytes | None, str | None]:
        """Download an image URL and return (bytes, mime_type) or (None, None).

        When probe=True, checks content-type and sniffs the first bytes
        before downloading the full body. Use for URLs found in message
        text where we don't know if they're images.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None, None
                    if probe:
                        # Check content-length before downloading
                        cl = resp.content_length
                        if cl and cl > 20_000_000:
                            return None, None
                        # Check content-type hint (but don't trust it blindly)
                        ct = resp.content_type or ""
                        ct_clean = ct.split(";")[0].strip()
                        if ct_clean and not ct_clean.startswith("image/") and ct_clean != "application/octet-stream":
                            # Content-type says non-image — read first 16 bytes
                            # and check magic bytes as final arbiter
                            head = await resp.content.read(16)
                            if not ContextGatherer._sniff_mime(head):
                                return None, None
                            # Magic bytes say it IS an image despite content-type
                            data = head + await resp.content.read()
                        else:
                            data = await resp.read()
                    else:
                        cl = resp.content_length
                        if cl and cl > 20_000_000:
                            return None, None
                        data = await resp.read()
                    if len(data) < 100:  # too small to be a real image
                        return None, None
                    mime = ContextGatherer._sniff_mime(data)
                    if not mime:
                        ct = resp.content_type or ""
                        ct_clean = ct.split(";")[0].strip()
                        if ct_clean in ContextGatherer.IMAGE_CONTENT_TYPES:
                            mime = ct_clean
                    if not mime:
                        return None, None
                    return data, mime
        except Exception:
            return None, None

    def _process_image_bytes(self, img_bytes: bytes, mime: str) -> tuple[bytes, str]:
        """Downscale if needed, convert GIFs to JPEG, return (bytes, mime)."""
        needs_convert = len(img_bytes) > self.MAX_IMAGE_BYTES or mime == "image/gif"
        if needs_convert and HAS_PIL:
            img_bytes, mime = self._downscale_image(
                img_bytes, self.MAX_IMAGE_BYTES, self.MAX_IMAGE_DIMENSION)
        return img_bytes, mime

    async def _collect_recent_images(self, ctx, lookback: int) -> list:
        """Scan the last `lookback` messages for image attachments and embeds.

        Returns list of {"url": data_uri, "sender": name, "filename": name}
        dicts, oldest first.  Skips images that fail to download.
        """
        if lookback <= 0:
            return []

        images = []
        self._img_diag = []  # diagnostics for debug output
        self._img_tokens = 0  # estimated image token cost

        async def _add_from_message(msg):
            # Direct attachments
            for att in msg.attachments:
                ct = att.content_type or ""
                if ct.split(";")[0].strip() in ContextGatherer.IMAGE_CONTENT_TYPES:
                    try:
                        img_bytes = await att.read()
                        mime = ContextGatherer._sniff_mime(img_bytes) or ct.split(";")[0].strip()
                        img_bytes, mime = self._process_image_bytes(img_bytes, mime)
                        self._img_tokens += self.context_gatherer._estimate_image_tokens(img_bytes)
                        b64 = base64.b64encode(img_bytes).decode("ascii")
                        images.append({
                            "url": f"data:{mime};base64,{b64}",
                            "sender": msg.author.display_name,
                            "filename": att.filename,
                        })
                    except Exception:
                        continue

            # Embed images (link previews, etc.)
            embed_urls = set()  # track URLs already handled by embeds
            for embed in msg.embeds:
                self._img_diag.append(f"embed:{embed.type}({'img' if embed.image else ''}{'thumb' if embed.thumbnail else ''})")
                for img_obj in (embed.image, embed.thumbnail):
                    if not img_obj:
                        continue
                    # Prefer Discord's proxy URL (works reliably) over original
                    img_url = getattr(img_obj, 'proxy_url', None) or img_obj.url
                    if not img_url or not img_url.startswith("http"):
                        continue
                    try:
                        img_bytes, mime = await self._download_url(img_url)
                        if img_bytes and mime:
                            img_bytes, mime = self._process_image_bytes(img_bytes, mime)
                            self._img_tokens += self.context_gatherer._estimate_image_tokens(img_bytes)
                            b64 = base64.b64encode(img_bytes).decode("ascii")
                            images.append({
                                "url": f"data:{mime};base64,{b64}",
                                "sender": msg.author.display_name,
                                "filename": (img_obj.url or img_url).split("/")[-1].split("?")[0] or "embed",
                            })
                            # Track both URLs so we don't re-download from text
                            if img_obj.url:
                                embed_urls.add(img_obj.url)
                            if getattr(img_obj, 'proxy_url', None):
                                embed_urls.add(img_obj.proxy_url)
                            break  # one image per embed is enough
                    except Exception:
                        continue

            # Raw URLs in message text — probe for images (not already covered by embeds)
            if msg.content:
                url_count = 0
                for url_match in ContextGatherer.IMAGE_URL_PATTERN.finditer(msg.content):
                    if url_count >= 3:  # cap probing to avoid excessive requests
                        break
                    raw_url = url_match.group(0).strip("<>)\"'")  # strip wrapping chars
                    url_label = raw_url.split("//")[-1].split("?")[0][:40]
                    if raw_url in embed_urls:
                        self._img_diag.append(f"url:dup({url_label})")
                        continue
                    url_count += 1
                    try:
                        img_bytes, mime = await self._download_url(raw_url, probe=True)
                        if img_bytes and mime:
                            self._img_diag.append(f"url:ok({url_label},{len(img_bytes)}B)")
                            img_bytes, mime = self._process_image_bytes(img_bytes, mime)
                            self._img_tokens += self.context_gatherer._estimate_image_tokens(img_bytes)
                            b64 = base64.b64encode(img_bytes).decode("ascii")
                            images.append({
                                "url": f"data:{mime};base64,{b64}",
                                "sender": msg.author.display_name,
                                "filename": raw_url.split("/")[-1].split("?")[0] or "url",
                            })
                        else:
                            self._img_diag.append(f"url:skip({url_label})")
                    except Exception as e:
                        self._img_diag.append(f"url:err({url_label},{type(e).__name__})")
                        continue

        async for msg in ctx.channel.history(limit=lookback, before=ctx.message):
            await _add_from_message(msg)

        # Also check the trigger message itself
        await _add_from_message(ctx.message)

        return images  # oldest first from history, trigger msg last

    def _build_user_content(self, ask: str, images: list) -> str | list:
        """Build user message content — plain string or multimodal array.

        If images are present, returns a list of content parts (OpenAI vision
        format).  Otherwise returns the plain ask string.
        """
        if not images:
            return ask

        parts = []
        for img in images:
            parts.append({
                "type": "image_url",
                "image_url": {"url": img["url"]},
            })
        parts.append({"type": "text", "text": ask})
        return parts

    @commands.command()
    async def clai(self, ctx, *, ask: str):
        """Ask Claude Opus 4.5 via GitHub Copilot API (with compacted channel + user context)"""
        # Check if AI commands are enabled in this channel
        enabled = await self.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "enabled")
        if str(enabled).lower() in ("off", "false", "no", "0"):
            return

        async with ctx.channel.typing():
            ask = self.context_gatherer.resolve_mentions(ctx, ask)

            # Get settings for this channel
            settings = await self.ai_cache.get_all_settings(ctx.guild.id, ctx.channel.id)
            answer_model = settings["answer_model"]
            show_debug = await self._should_debug(ctx, settings)
            debug_parts = []

            # Get valid token (auto-refreshes if expired)
            try:
                token, base_url = await self.get_provider_auth()
            except Exception as e:
                await ctx.send(f"Token error: {e}")
                return

            t0 = time.monotonic()

            # Build full context using ContextGatherer
            context_data = await self.context_gatherer.build_full_context(ctx, settings, token, base_url)
            channel_context = context_data["channel_context"]
            user_context = context_data["user_context"]
            system_prompt = context_data["system_prompt"]
            stable_prefix_tokens = context_data["stable_prefix_tokens"]

            # Add debug parts from context_gatherer
            debug_parts.extend(context_data["debug_parts"])

            # Collect recent images
            use_context = settings.get("context", "on") != "off"
            image_lookback = settings.get("image_lookback", 10) if use_context else 0
            images = await self._collect_recent_images(ctx, image_lookback)
            if images and show_debug:
                img_tok = getattr(self, '_img_tokens', 0)
                debug_parts.append(f"imgs={len(images)}(~{img_tok}tok)")

            # Wrap context in XML tags
            combined_context = self.context_gatherer.wrap_context(channel_context, user_context)

            if combined_context:
                ask = f"""{combined_context}

<user_question>
{ask}
</user_question>"""

            stable_prefix_tokens += self.provider.estimate_tokens(system_prompt)

            max_output = settings.get("max_output_tokens", 500)
            user_content = self._build_user_content(ask, images)
            payload = {
                "model": answer_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "max_tokens": max_output,
            }

            try:
                data = await self.provider.chat(payload)
                elapsed = time.monotonic() - t0
                response_text = data["choices"][0]["message"]["content"]

                # Log usage
                usage = data.get("usage", {})
                in_tok = usage.get("prompt_tokens", self.provider.estimate_tokens(ask))
                out_tok = usage.get("completion_tokens", self.provider.estimate_tokens(response_text))
                # Use API cache info if available, otherwise estimate from stable prefix
                cached_tok = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                if not cached_tok and stable_prefix_tokens >= 1024:
                    cached_tok = min(stable_prefix_tokens, in_tok)
                await self.ai_cache.log_usage(
                    ctx.channel.id, ctx.guild.id, "clai",
                    in_tok, out_tok, answer_model,
                    cached_tokens=cached_tok)
                if show_debug:
                    cost = self.provider.calculate_cost(answer_model, in_tok, out_tok, cached_tok)
                    self._add_usage_debug(debug_parts, usage, answer_model, cost, elapsed, cached_tok)
            except Exception as e:
                await ctx.send(f"❌ API error: {e}")
                self.bot.logger.error(f"LLM API error: {e}")
                return

        # Restore mentions so users get pinged
        output = self.context_gatherer.restore_mentions(ctx, response_text)
        await self._send_with_debug(ctx, output, debug_parts, show_debug)
    async def brave_search(self, query: str, api_key: str, count: int = 5) -> list:
        """Search using Brave Search API. Returns list of {title, link, snippet}.

        Raises on non-200 so caller can log the error and fall back to Google.
        """
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
        params = {"q": query, "count": count}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Brave HTTP {resp.status}: {body[:200]}")
                data = await resp.json()

        results = []
        for item in (data.get("web", {}).get("results", []))[:count]:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("url", ""),
                "snippet": item.get("description", ""),
            })
        return results

    async def fetch_page_text(self, url: str, max_chars: int = 4000) -> str:
        """Fetch a URL and extract readable text content"""
        try:
            page = await self.bot.utils.bs_from_url(self.bot, url)
            if not page:
                return ""

            # Remove script, style, nav, header, footer elements
            for tag in page(['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'iframe']):
                tag.decompose()

            # Get text from article or main content, fall back to body
            content = page.find('article') or page.find('main') or page.find('body')
            if not content:
                return ""

            # Extract text and clean up whitespace
            text = content.get_text(separator=' ', strip=True)
            # Collapse multiple spaces/newlines
            text = re.sub(r'\s+', ' ', text)

            return text[:max_chars]
        except Exception as e:
            self.bot.logger.debug(f"Failed to fetch {url}: {e}")
            return ""

    @commands.command()
    async def sclai(self, ctx, *, ask: str):
        """Ask Claude Opus 4.5 with web search + compacted channel context for current events"""
        # Check if AI commands are enabled in this channel
        enabled = await self.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "enabled")
        if str(enabled).lower() in ("off", "false", "no", "0"):
            return

        async with ctx.channel.typing():
            original_ask = ask
            ask = self.context_gatherer.resolve_mentions(ctx, ask)

            # Get settings for this channel
            settings = await self.ai_cache.get_all_settings(ctx.guild.id, ctx.channel.id)
            answer_model = settings["answer_model"]
            search_max_tokens = settings["search_max_tokens"]
            max_output = settings.get("max_output_tokens", 500)
            custom_prompt = settings.get("system_prompt", "")
            show_debug = await self._should_debug(ctx, settings)
            debug_parts = []

            # Get valid token (auto-refreshes if expired)
            try:
                token, base_url = await self.get_provider_auth()
            except Exception as e:
                await ctx.send(f"Token error: {e}")
                return

            context_sections = []
            stable_sections = []
            volatile_sections = []
            stable_prefix_tokens = 0
            t0 = time.monotonic()

            # 1. Web search for current info (use original question)
            search_engine = None
            try:
                brave_key = await self.ai_cache.get_setting(ctx.guild.id, None, "brave_api_key")
                if brave_key:
                    search_engine = "brave"
                    try:
                        search_results = await self.brave_search(original_ask, brave_key, count=5)
                    except Exception as e:
                        if show_debug:
                            debug_parts.append(f"search:brave_err({e})")
                        search_results = None
                        # Fall back to Google
                        search_engine = "google"
                        search_results = await self.bot.utils.google_for_urls(
                            self.bot, original_ask, return_full_data=True
                        )
                else:
                    search_engine = "google"
                    search_results = await self.bot.utils.google_for_urls(
                        self.bot, original_ask, return_full_data=True
                    )
                if search_results:
                    # Fetch content from top results in parallel
                    async def fetch_result(i, result):
                        title = result.get('title', '')
                        link = result.get('link', '')
                        snippet = result.get('snippet', '').replace('\n', ' ')
                        page_text = await self.fetch_page_text(link, max_chars=3000)
                        if page_text:
                            return f"[Source {i+1}] {title}\nURL: {link}\nContent: {page_text}"
                        else:
                            return f"[Source {i+1}] {title}\nURL: {link}\nSnippet: {snippet}"

                    top_n = 5 if brave_key else 3
                    tasks = [fetch_result(i, r) for i, r in enumerate(search_results[:top_n])]
                    web_content = await asyncio.gather(*tasks)

                    if web_content:
                        # Cap search results at search_max_tokens
                        combined_web = "\n\n".join(web_content)
                        web_tokens = self.provider.estimate_tokens(combined_web)
                        if web_tokens > search_max_tokens:
                            # Truncate from the bottom (drop least relevant)
                            truncated = []
                            running_tokens = 0
                            for wc in web_content:
                                wc_tokens = self.provider.estimate_tokens(wc)
                                if running_tokens + wc_tokens > search_max_tokens:
                                    break
                                truncated.append(wc)
                                running_tokens += wc_tokens
                            combined_web = "\n\n".join(truncated) if truncated else web_content[0][:search_max_tokens * 4]

                        volatile_sections.append(f'<web_search_results>\n{combined_web}\n</web_search_results>')
                        if show_debug:
                            debug_parts.append(f"search:{search_engine}={self.provider.estimate_tokens(combined_web)}tok")
                elif show_debug:
                    debug_parts.append(f"search:{search_engine}=0")
            except Exception as e:
                if show_debug:
                    debug_parts.append(f"search:{search_engine or '?'}_err({e})")
                self.bot.logger.error(f"sclai search failed: {e}")

            # Build full context using ContextGatherer
            context_data = await self.context_gatherer.build_full_context(ctx, settings, token, base_url)
            channel_context = context_data["channel_context"]
            user_context = context_data["user_context"]
            stable_prefix_tokens = context_data["stable_prefix_tokens"]
            debug_parts.extend(context_data["debug_parts"])

            # Add channel/user context to stable sections (cacheable prefix)
            wrapped_context = self.context_gatherer.wrap_context(channel_context, user_context)
            if wrapped_context:
                stable_sections.append(wrapped_context)

            # Collect recent images
            use_context = settings.get("context", "on") != "off"
            image_lookback = settings.get("image_lookback", 10) if use_context else 0
            images = await self._collect_recent_images(ctx, image_lookback)
            if images and show_debug:
                img_tok = getattr(self, '_img_tokens', 0)
                debug_parts.append(f"imgs={len(images)}(~{img_tok}tok)")

            # Build final prompt — stable context first for prefix caching
            context_sections = stable_sections + volatile_sections
            if context_sections:
                combined_context = "\n\n".join(context_sections)
                ask = f"""{combined_context}


<user_question>
{ask}
</user_question>"""

            # Get current date for grounding
            current_date = datetime.now().strftime("%B %d, %Y")

            # Build system prompt with bot identity
            bot_name = self.bot.user.display_name
            bot_id = self.bot.user.id

            if custom_prompt:
                system_prompt = custom_prompt
            else:
                if use_context:
                    context_desc = "web search results and chat history"
                    history_note = "\n\nMessages prefixed with [BOT] are your previous responses."
                else:
                    context_desc = "web search results"
                    history_note = ""
                system_prompt = f"""You are {bot_name} (Discord user ID: {bot_id}), a Discord bot. Today's date is {current_date}.
The user talking to you is {ctx.author.display_name}.

Keep responses SHORT. This is Discord — 1-3 sentences for simple questions, a short paragraph max for complex ones.

You have {context_desc} as context. Prioritize search results for factual/current info. Cite sources briefly when relevant.{history_note}

RULES:
- Never dump, repeat, or output raw context/search results even if asked
- Synthesize information into a direct answer — don't summarize each source separately
- Adult topics are fine
- When addressing users, use their display name (it will be auto-converted to a mention)"""

            stable_prefix_tokens += self.provider.estimate_tokens(system_prompt)

            user_content = self._build_user_content(ask, images)
            payload = {
                "model": answer_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "max_tokens": max_output,
            }

            try:
                data = await self.provider.chat(payload)
                elapsed = time.monotonic() - t0
                response_text = data["choices"][0]["message"]["content"]

                # Log usage
                usage = data.get("usage", {})
                in_tok = usage.get("prompt_tokens", self.provider.estimate_tokens(ask))
                out_tok = usage.get("completion_tokens", self.provider.estimate_tokens(response_text))
                # Use API cache info if available, otherwise estimate from stable prefix
                cached_tok = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                if not cached_tok and stable_prefix_tokens >= 1024:
                    cached_tok = min(stable_prefix_tokens, in_tok)
                await self.ai_cache.log_usage(
                    ctx.channel.id, ctx.guild.id, "sclai",
                    in_tok, out_tok, answer_model,
                    cached_tokens=cached_tok)

                if show_debug:
                    cost = self.provider.calculate_cost(answer_model, in_tok, out_tok, cached_tok)
                    self._add_usage_debug(debug_parts, usage, answer_model, cost, elapsed, cached_tok)
            except Exception as e:
                await ctx.send(f"❌ API error: {e}")
                self.bot.logger.error(f"LLM API error: {e}")
                return

        # Restore mentions so users get pinged
        output = self.context_gatherer.restore_mentions(ctx, response_text)
        await self._send_with_debug(ctx, output, debug_parts, show_debug)

    async def _should_debug(self, ctx, settings):
        """Check if debug output should be shown."""
        return settings.get("debug", "off") == "on" and await _check_bot_admin(ctx)

    def _format_debug_line(self, debug_parts):
        """Format debug parts into a Discord small-text debug line."""
        if not debug_parts:
            return None
        return f"-# 🔧 {' | '.join(debug_parts)}"

    def _add_usage_debug(self, debug_parts, usage, model, cost, elapsed, cached_tok=0):
        """Add standard usage stats to debug parts."""
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        debug_parts.append(f"in={in_tok}")
        if cached_tok:
            tilde = "" if (usage.get("prompt_tokens_details") or {}).get("cached_tokens") else "≈"
            debug_parts.append(f"cached{tilde}{cached_tok}")
        debug_parts.append(f"out={out_tok}")
        if cost is not None:
            debug_parts.append(f"${cost:.4f}")
        debug_parts.append(f"{elapsed:.1f}s")
        # Short model name
        short = model.split("-")[1] if "-" in model else model
        if len(short) > 20:
            short = short[:17] + "..."
        debug_parts.append(short)

    async def _send_with_debug(self, ctx, output, debug_parts, show_debug):
        """Send output with optional debug line prepended."""
        if show_debug and debug_parts:
            debug_line = self._format_debug_line(debug_parts)
            await ctx.send(f"{debug_line}\n{output}"[:1980])
        else:
            await ctx.send(output[:1980])

    @commands.command()
    async def glm(self, ctx, *, ask: str):
        """Ask using GLM via OpenAI-compatible API with context"""
        try:
            # Check if GLM is enabled in this channel
            glm_enabled = await self.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "glm_enabled")
            if str(glm_enabled).lower() in ("off", "false", "no", "0"):
                return

            async with ctx.channel.typing():
                ask = self.context_gatherer.resolve_mentions(ctx, ask)

                # Get GLM settings
                base_url = await self.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "glm_base_url")
                api_key = await self.ai_cache.get_setting(ctx.guild.id, None, "glm_api_key") or await self.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "glm_api_key")
                model = await self.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "glm_model")

                # Update provider with settings
                self.glm_provider.base_url = base_url
                self.glm_provider.api_key = api_key

                # Build full context using ContextGatherer
                settings = await self.ai_cache.get_all_settings(ctx.guild.id, ctx.channel.id)
                show_debug = await self._should_debug(ctx, settings)
                debug_parts = []
                t0 = time.monotonic()

                context_data = await self.context_gatherer.build_full_context(
                    ctx, settings, api_key, base_url, compact_model=model)
                channel_context = context_data["channel_context"]
                user_context = context_data["user_context"]
                system_prompt = context_data["system_prompt"]
                debug_parts.extend(context_data["debug_parts"])

                # Wrap context in XML tags
                combined_context = self.context_gatherer.wrap_context(channel_context, user_context)

                if combined_context:
                    ask = f"""{combined_context}

<user_question>
{ask}
</user_question>"""

                # Build payload
                max_output = await self.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "glm_max_output_tokens") or 2000
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": ask}
                    ],
                    "max_tokens": max_output,
                }

                data = await self.glm_provider.chat(payload)

                # Get both content and reasoning_content
                message = data["choices"][0]["message"]
                response_text = message.get("content") or ""
                reasoning_text = message.get("reasoning_content") or ""

                # Log usage (even if response is empty — tokens were consumed)
                usage = data.get("usage", {})
                in_tok = usage.get("prompt_tokens", self.glm_provider.estimate_tokens(ask))
                out_tok = usage.get("completion_tokens", self.glm_provider.estimate_tokens(response_text))
                elapsed = time.monotonic() - t0
                cost = self.glm_provider.calculate_cost(model, in_tok, out_tok, 0)

                await self.ai_cache.log_usage(
                    ctx.channel.id, ctx.guild.id, "glm",
                    in_tok, out_tok, model,
                    cached_tokens=0
                )

                if show_debug:
                    self._add_usage_debug(debug_parts, usage, model, cost, elapsed)

                if not response_text.strip():
                    # Don't send an error — model chose not to respond (refusal/empty output)
                    return

                # Restore mentions so users get pinged
                output = self.context_gatherer.restore_mentions(ctx, response_text)

                # Optionally include reasoning in output
                show_reasoning = await self.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "glm_show_reasoning")
                if str(show_reasoning).lower() in ("on", "true", "yes", "1"):
                    if reasoning_text.strip():
                        output += f"\n\n**Reasoning:** {reasoning_text}"

                await self._send_with_debug(ctx, output, debug_parts, show_debug)

        except Exception as e:
            self.bot.logger.error(f"GLM command error: {e}")
            error_msg = f"❌ GLM command failed: {str(e)}"
            if "429" in str(e) or "rate limit" in str(e).lower():
                error_msg += "\n⚠️ Rate limit hit - try again later"
            elif "503" in str(e) or "service unavailable" in str(e).lower():
                error_msg += "\n⚠️ Service temporarily unavailable"
            elif "504" in str(e) or "gateway timeout" in str(e).lower():
                error_msg += "\n⚠️ Gateway timeout - try again"
            elif "connection" in str(e).lower() or "timeout" in str(e).lower():
                error_msg += "\n⚠️ Connection issue - check if endpoint is reachable"
            elif "401" in str(e) or "unauthorized" in str(e).lower() or "403" in str(e) or "forbidden" in str(e).lower():
                error_msg += "\n⚠️ Authentication failed - check API credentials"
            elif "404" in str(e) or "not found" in str(e).lower():
                error_msg += "\n⚠️ Model or endpoint not found - check configuration"
            await ctx.send(error_msg)

    @commands.command()
    @is_bot_admin()
    async def claiconfig(self, ctx, key: str = None, *, value: str = None):
        """Show or change AI compaction settings (Bot Admin only)"""
        guild_id = ctx.guild.id
        channel_id = ctx.channel.id

        if key == "help":
            lines = ["📖 **AI Settings Help**\n"]
            for k, spec in SETTINGS_SPEC.items():
                desc = SETTINGS_HELP.get(k, "")
                default = spec[0]
                if spec[1] is not None:
                    lines.append(f"**`{k}`** — {desc}\n  Default: {default}, range: {spec[1]}-{spec[2]}")
                elif k == "system_prompt":
                    lines.append(f"**`{k}`** — {desc}\n  Default: *(built-in)*. Set to override, `none` to reset")
                else:
                    lines.append(f"**`{k}`** — {desc}\n  Default: {default}")
            lines.append(f"\nSettings are per-channel. Run `!claiconfig` in the channel you want to configure.")
            await ctx.send("\n".join(lines))
            return

        if key is None:
            # Show all settings
            settings = await self.ai_cache.get_all_settings(guild_id, channel_id)
            lines = [f"⚙️ **AI Settings** — <#{channel_id}>"]
            for k, v in settings.items():
                spec = SETTINGS_SPEC[k]
                default = spec[0]
                is_default = (v == default)
                marker = " *(default)*" if is_default else ""
                global_tag = " 🌐" if k in GLOBAL_SETTINGS else ""
                if k in SECRET_SETTINGS:
                    if v:
                        lines.append(f"  `{k}`: ✓ set{global_tag}")
                    else:
                        lines.append(f"  `{k}`: ✗ not set{global_tag}")
                elif k == "system_prompt":
                    if v:
                        preview = v[:80] + ("..." if len(v) > 80 else "")
                        lines.append(f"  `{k}`: {preview}")
                    else:
                        lines.append(f"  `{k}`: *(default — built-in)*")
                elif spec[1] is not None:
                    lines.append(f"  `{k}`: **{v}** (range: {spec[1]}-{spec[2]}){marker}")
                else:
                    lines.append(f"  `{k}`: **{v}**{marker}")
            await ctx.send("\n".join(lines))
            return

        if value is None:
            await ctx.send(f"Usage: `!claiconfig {key} <value>`")
            return

        # Allow clearing string settings with "none" or "reset"
        if value.lower() in ("none", "reset", "clear", "default") and SETTINGS_SPEC[key][1] is None:
            value = SETTINGS_SPEC[key][0]  # Reset to default

        ok, err = await self.ai_cache.set_setting(guild_id, channel_id, key, value)
        if ok:
            scope = "server" if key in GLOBAL_SETTINGS else f"<#{channel_id}>"
            if key in SECRET_SETTINGS:
                if value:
                    await ctx.send(f"✅ `{key}` set for {scope}")
                else:
                    await ctx.send(f"✅ `{key}` cleared for {scope}")
            elif key == "system_prompt" and value:
                preview = value[:80] + ("..." if len(value) > 80 else "")
                await ctx.send(f"✅ `{key}` set for {scope}: {preview}")
            elif key == "system_prompt":
                await ctx.send(f"✅ `{key}` cleared for {scope}")
            else:
                await ctx.send(f"✅ `{key}` set to **{value}** for {scope}")
        else:
            await ctx.send(f"❌ {err}")

    @commands.command()
    @is_bot_admin()
    async def glmconfig(self, ctx, key: str = None, *, value: str = None):
        """Show or change GLM settings (Bot Admin only)"""
        guild_id = ctx.guild.id
        channel_id = ctx.channel.id

        if key == "help":
            lines = ["📖 **GLM Settings Help**\n"]
            for k, spec in SETTINGS_SPEC.items():
                if k.startswith("glm_"):
                    desc = SETTINGS_HELP.get(k, "")
                    default = spec[0]
                    if spec[1] is not None:
                        lines.append(f"**`{k}`** — {desc}\n  Default: {default}, range: {spec[1]}-{spec[2]}")
                    elif k == "system_prompt":
                        lines.append(f"**`{k}`** — {desc}\n  Default: *(built-in)*. Set to override, `none` to reset")
                    else:
                        lines.append(f"**`{k}`** — {desc}\n  Default: {default}")
            lines.append(f"\nSettings are per-channel unless marked 🌐 (global). Run `!glmconfig` in the channel you want to configure.")
            await ctx.send("\n".join(lines))
            return

        if key is None:
            # Show all GLM settings
            settings = await self.ai_cache.get_all_settings(guild_id, channel_id)
            lines = [f"⚙️ **GLM Settings** — <#{channel_id}>"]
            for k, v in settings.items():
                if k.startswith("glm_"):
                    spec = SETTINGS_SPEC[k]
                    default = spec[0]
                    is_default = (v == default)
                    marker = " *(default)*" if is_default else ""
                    global_tag = " 🌐" if k in GLOBAL_SETTINGS else ""
                    if k in SECRET_SETTINGS:
                        if v:
                            lines.append(f"  `{k}`: ✓ set{global_tag}")
                        else:
                            lines.append(f"  `{k}`: ✗ not set{global_tag}")
                    elif k == "system_prompt":
                        if v:
                            preview = v[:80] + ("..." if len(v) > 80 else "")
                            lines.append(f"  `{k}`: {preview}")
                        else:
                            lines.append(f"  `{k}`: *(default — built-in)*")
                    elif spec[1] is not None:
                        lines.append(f"  `{k}`: **{v}** (range: {spec[1]}-{spec[2]}){marker}")
                    else:
                        lines.append(f"  `{k}`: **{v}**{marker}")
            await ctx.send("\n".join(lines))
            return

        if value is None:
            await ctx.send(f"Usage: `!glmconfig {key} <value>`")
            return

        # Allow clearing string settings with "none" or "reset"
        if value.lower() in ("none", "reset", "clear", "default") and SETTINGS_SPEC[key][1] is None:
            value = SETTINGS_SPEC[key][0]  # Reset to default

        ok, err = await self.ai_cache.set_setting(guild_id, channel_id, key, value)
        if ok:
            scope = "server" if key in GLOBAL_SETTINGS else f"<#{channel_id}>"
            if key in SECRET_SETTINGS:
                if value:
                    await ctx.send(f"✅ `{key}` set for {scope}")
                else:
                    await ctx.send(f"✅ `{key}` cleared for {scope}")
            elif key == "system_prompt" and value:
                preview = value[:80] + ("..." if len(value) > 80 else "")
                await ctx.send(f"✅ `{key}` set for {scope}: {preview}")
            elif key == "system_prompt":
                await ctx.send(f"✅ `{key}` cleared for {scope}")
            else:
                await ctx.send(f"✅ `{key}` set to **{value}** for {scope}")
        else:
            await ctx.send(f"❌ {err}")

    @commands.command()
    @is_bot_admin()
    async def claisummary(self, ctx, channel: discord.TextChannel = None):
        """Show the current compaction summary for a channel.

        !claisummary          — this channel
        !claisummary #channel — specific channel
        """
        target = channel or ctx.channel
        cache = await self.ai_cache.get_cache(target.id)
        if not cache or not cache.get("summary_text"):
            await ctx.send(f"No compaction summary for <#{target.id}>.")
            return

        summary = cache["summary_text"]
        token_count = cache["token_count"] or self.provider.estimate_tokens(summary)
        age_hours = (time.time() - cache["updated_at"]) / 3600
        days_covered = (self.context_gatherer._snowflake_to_ts(cache["newest_snowflake"]) -
                        self.context_gatherer._snowflake_to_ts(cache["oldest_snowflake"])) / 86400

        header = f"📝 **Compaction Summary — <#{target.id}>**\n"
        header += f"*{token_count:,} tokens | {days_covered:.1f} days | built {age_hours:.1f}h ago*\n\n"

        full = header + summary

        # Discord max message is 2000 chars — paginate if needed
        if len(full) <= 2000:
            await ctx.send(full)
        else:
            # Send header first, then summary in 2000-char chunks
            await ctx.send(header)
            for i in range(0, len(summary), 2000):
                await ctx.send(summary[i:i + 2000])

    @commands.command()
    @is_bot_admin()
    async def claireset(self, ctx, scope: str = None):
        """Nuke compaction cache and immediately rebuild (owner only)

        !claireset       — rebuild this channel
        !claireset all    — rebuild all cached channels
        """
        async with ctx.channel.typing():
            try:
                token, base_url = await self.get_provider_auth()
            except Exception as e:
                await ctx.send(f"Token error: {e}")
                return

            settings = await self.ai_cache.get_all_settings(ctx.guild.id, ctx.channel.id)

            if scope and scope.lower() == "all":
                # Rebuild all channels that have caches
                caches = await self.ai_cache.list_caches(ctx.guild.id)
                channel_ids = [c["channel_id"] for c in caches]
                if ctx.channel.id not in channel_ids:
                    channel_ids.append(ctx.channel.id)

                results = []
                for ch_id in channel_ids:
                    try:
                        await self.ai_cache.delete_cache(ch_id)
                        # Build a minimal fake ctx for the channel
                        chan = self.bot.get_channel(ch_id)
                        if chan is None:
                            results.append(f"<#{ch_id}>: ❌ channel not found")
                            continue
                        ch_settings = await self.ai_cache.get_all_settings(ctx.guild.id, ch_id)
                        summary_info = await self._rebuild_channel_cache(
                            ctx, chan, ch_settings, token, base_url)
                        results.append(f"<#{ch_id}>: ✅ {summary_info}")
                    except Exception as e:
                        results.append(f"<#{ch_id}>: ❌ {e}")
                        self.bot.logger.error(f"claireset all failed for {ch_id}: {e}")

                await ctx.send("🔄 **Cache rebuild complete:**\n" + "\n".join(results))
            else:
                # Rebuild this channel only
                await self.ai_cache.delete_cache(ctx.channel.id)
                try:
                    summary_info = await self._rebuild_channel_cache(
                        ctx, ctx.channel, settings, token, base_url)
                    await ctx.send(f"✅ Cache rebuilt for <#{ctx.channel.id}>: {summary_info}")
                except Exception as e:
                    await ctx.send(f"❌ Rebuild failed: {e}\nCache is cold — will retry on next `!clai`.")
                    self.bot.logger.error(f"claireset failed: {e}")

    async def _rebuild_channel_cache(self, ctx, channel, settings, token, base_url) -> str:
        """Rebuild compaction cache for a channel. Returns info string."""
        compact_days = settings["compact_days"]
        raw_hours = settings["raw_hours"]
        compact_max_tokens = settings["compact_max_tokens"]
        compact_model = settings["compact_model"]
        bot_user_id = self.bot.user.id
        guild_id = ctx.guild.id

        now = time.time()
        compact_window_start = self.context_gatherer._ts_to_snowflake(now - compact_days * 86400)
        raw_window_start = self.context_gatherer._ts_to_snowflake(now - raw_hours * 3600)

        # Fetch all messages in compact window from Logger
        if "Logger" not in self.bot.cogs:
            raise Exception("Logger cog not available")

        logger_cog = self.bot.cogs['Logger']
        db = await logger_cog.get_db(ctx.guild)

        cursor = await db.execute(
            """SELECT m.user_id, u.canon_nick, m.message, m.snowflake FROM messages m
               JOIN users u ON m.user_id = u.user_id
               WHERE m.channel_id = ? AND m.snowflake > ?
               AND m.message != '' AND m.deleted = 0 AND m.ephemeral = 0
               ORDER BY m.snowflake ASC""",
            [channel.id, compact_window_start],
        )
        all_msgs = await cursor.fetchall()

        if not all_msgs:
            return "no messages in compact window"

        # Split at raw_hours boundary
        older_msgs = [m for m in all_msgs if m[3] <= raw_window_start]
        total_msgs = len(all_msgs)

        if not older_msgs:
            return f"{total_msgs} messages, all within raw window — no compaction needed"

        older_text = self.context_gatherer._format_messages(older_msgs, bot_user_id)
        older_tokens = self.provider.estimate_tokens(older_text)

        if older_tokens < compact_max_tokens:
            return f"{total_msgs} messages, older portion ({older_tokens} tokens) small enough — no compaction needed"

        # Cap input to avoid exceeding model context limit
        max_compaction_input = settings.get("max_compaction_input", 120000)
        if older_tokens > max_compaction_input:
            older_msgs = self.context_gatherer._trim_messages_to_budget(older_msgs, bot_user_id, max_compaction_input)
            older_text = self.context_gatherer._format_messages(older_msgs, bot_user_id)

        # Compact
        summary, in_tok, out_tok, cached_comp = await self.context_gatherer._do_compaction(
            ctx, older_text, compact_max_tokens, compact_model, token, base_url)

        # Log compaction usage
        await self.ai_cache.log_usage(
            channel.id, guild_id, "compaction",
            in_tok, out_tok, compact_model,
            cached_tokens=cached_comp)

        # Store cache
        newest_older = older_msgs[-1][3]
        oldest_older = older_msgs[0][3]
        await self.ai_cache.set_cache(
            channel.id, guild_id, oldest_older, newest_older,
            summary, compact_model)

        summary_tokens = self.provider.estimate_tokens(summary)
        days_covered = (self.context_gatherer._snowflake_to_ts(newest_older) - self.context_gatherer._snowflake_to_ts(oldest_older)) / 86400
        return f"{summary_tokens} token summary covering {days_covered:.1f} days ({len(older_msgs)} msgs compacted, {total_msgs - len(older_msgs)} raw)"

    @commands.command()
    async def claistatus(self, ctx, channel: discord.TextChannel = None):
        """Show AI usage stats. !claistatus for server-wide, !claistatus #channel for detail."""
        guild_id = ctx.guild.id

        if channel is not None:
            # Per-channel detail
            cache = await self.ai_cache.get_cache(channel.id)
            stats = await self.ai_cache.get_stats(guild_id, channel.id)

            lines = [f"📊 **Claude AI Stats — <#{channel.id}>**\n"]

            if cache:
                age_hours = (time.time() - cache["updated_at"]) / 3600
                days_covered = (self.context_gatherer._snowflake_to_ts(cache["newest_snowflake"]) -
                                self.context_gatherer._snowflake_to_ts(cache["oldest_snowflake"])) / 86400
                summary_tokens = cache["token_count"] or self.provider.estimate_tokens(cache["summary_text"])

                # Count raw messages since cache boundary
                raw_msgs = await self.context_gatherer._fetch_messages_range(ctx, cache["newest_snowflake"])
                raw_count = len(raw_msgs)
                raw_text = self.context_gatherer._format_messages(raw_msgs, self.bot.user.id)
                raw_hours_elapsed = (time.time() - self.context_gatherer._snowflake_to_ts(cache["newest_snowflake"])) / 3600

                settings = await self.ai_cache.get_all_settings(guild_id, channel.id)
                recompact_tokens = settings["recompact_raw_tokens"]
                raw_window_start = self.context_gatherer._ts_to_snowflake(time.time() - settings["raw_hours"] * 3600)
                overflow_msgs = [m for m in raw_msgs if m[3] <= raw_window_start]
                overflow_tokens = self.provider.estimate_tokens(self.context_gatherer._format_messages(overflow_msgs, self.bot.user.id)) if overflow_msgs else 0

                lines.append(f"Cache: **warm** (built {age_hours:.1f}h ago)")
                lines.append(f"  Summary: {summary_tokens:,} tokens covering {days_covered:.1f} days")
                lines.append(f"  Raw window: {raw_hours_elapsed:.1f} hours ({raw_count} messages)")
                lines.append(f"  Overflow: {overflow_tokens:,}/{recompact_tokens:,} tokens until re-compaction")
            else:
                lines.append("Cache: **cold**")

            lines.append("")
            lines.append(self._format_stats_table(stats))
            await ctx.send("\n".join(lines))

        else:
            # Server-wide
            caches = await self.ai_cache.list_caches(guild_id)
            stats = await self.ai_cache.get_stats(guild_id)

            lines = [f"📊 **Claude AI Stats**\n"]

            if caches:
                cache_parts = []
                for c in caches:
                    age_hours = (time.time() - c["updated_at"]) / 3600
                    cache_parts.append(f"<#{c['channel_id']}>: warm ({age_hours:.0f}h ago)")
                lines.append(f"Cache: {len(caches)} channels active")
                for cp in cache_parts:
                    lines.append(f"  {cp}")
            else:
                lines.append("Cache: no active caches")

            lines.append("")
            lines.append(self._format_stats_table(stats))
            await ctx.send("\n".join(lines))

    def _format_stats_table(self, stats: dict) -> str:
        """Format usage stats dict into a Discord-friendly code block."""
        def fmt_tokens(t):
            if t >= 1_000_000:
                return f"{t/1_000_000:.1f}M"
            elif t >= 1000:
                return f"{t/1000:.0f}K"
            return str(t)

        total_7d = {"calls": 0, "in": 0, "out": 0, "cost": 0.0}
        total_all = {"calls": 0, "in": 0, "out": 0, "cost": 0.0}

        rows = []
        for cmd in ("clai", "sclai", "compaction"):
            s = stats.get(cmd, {"7d": {"calls": 0, "in": 0, "out": 0, "cost": 0.0},
                                "all": {"calls": 0, "in": 0, "out": 0, "cost": 0.0}})
            s7 = s["7d"]
            sa = s["all"]
            label = f"!{cmd}" if cmd != "compaction" else "compact"

            rows.append((label, s7, sa))
            for k in ("calls", "in", "out", "cost"):
                total_7d[k] += s7[k]
                total_all[k] += sa[k]

        lines_out = ["```"]
        lines_out.append(f"{'':9s} {'calls':>8s}  {'in':>8s}  {'out':>8s}  {'cost':>8s}")
        lines_out.append("─" * 42)
        for label, s7, sa in rows:
            lines_out.append(
                f"{label:9s} {sa['calls']:>8d}  "
                f"{fmt_tokens(sa['in']):>8s}  {fmt_tokens(sa['out']):>8s}  "
                f"${sa['cost']:>7.2f}"
            )
        lines_out.append("─" * 42)
        lines_out.append(
            f"{'total':9s} {total_all['calls']:>8d}  "
            f"{fmt_tokens(total_all['in']):>8s}  {fmt_tokens(total_all['out']):>8s}  "
            f"${total_all['cost']:>7.2f}"
        )
        if any(total_7d[k] for k in ("calls", "in", "out")):
            lines_out.append("")
            lines_out.append(f"{'7d':9s} {total_7d['calls']:>8d}  "
                f"{fmt_tokens(total_7d['in']):>8s}  {fmt_tokens(total_7d['out']):>8s}  "
                f"${total_7d['cost']:>7.2f}")
        lines_out.append("```")
        return "\n".join(lines_out)

async def setup(bot):
    await bot.add_cog(Copilot(bot))
