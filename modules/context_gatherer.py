"""Context gathering and compaction logic for Discord bot.

This module provides shared context-gathering functionality for commands like !clai, !sclai, and !glm.
"""

import aiohttp
import asyncio
import io
import re
import time
from datetime import datetime

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from modules.ai_cache import AICache


class ContextGatherer:
    """Gathers and compacts Discord conversation context for AI commands."""

    DISCORD_EPOCH = 1420070400000  # Jan 1, 2015 in ms

    IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    IMAGE_URL_PATTERN = re.compile(r'https?://\S+', re.IGNORECASE)
    MAX_IMAGE_BYTES = 3_500_000  # ~3.5MB raw; base64 is ~33% larger → ~4.7MB (API limit ~5MB)
    MAX_IMAGE_DIMENSION = 2048   # max width or height in pixels

    def __init__(self, bot, ai_cache: AICache, provider):
        self.bot = bot
        self.ai_cache = ai_cache
        # provider is used for estimate_tokens() only — all providers use the
        # same len(text)//4 heuristic, so it doesn't matter which is passed.
        self.provider = provider

    def resolve_mentions(self, ctx, text: str) -> str:
        """Replace Discord mention IDs with display names"""
        for user in ctx.message.mentions:
            text = text.replace(f'<@{user.id}>', user.display_name)
            text = text.replace(f'<@!{user.id}>', user.display_name)
        return text

    def restore_mentions(self, ctx, text: str) -> str:
        """Replace display names back to Discord mentions in output"""
        # Build name→mention map from message mentions + command author
        mention_map = {}
        for user in ctx.message.mentions:
            mention_map[user.display_name] = f'<@{user.id}>'
            if hasattr(user, 'name') and user.name != user.display_name:
                mention_map[user.name] = f'<@{user.id}>'
        # Always include the command invoker
        author = ctx.author
        mention_map[author.display_name] = f'<@{author.id}>'
        if hasattr(author, 'name') and author.name != author.display_name:
            mention_map[author.name] = f'<@{author.id}>'
        # Replace longest names first to avoid partial matches
        for name in sorted(mention_map, key=len, reverse=True):
            text = text.replace(name, mention_map[name])
        return text

    def _ts_to_snowflake(self, timestamp_s: float) -> int:
        """Convert a Unix timestamp (seconds) to a Discord snowflake."""
        return (int(timestamp_s * 1000) - self.DISCORD_EPOCH) << 22

    def _snowflake_to_ts(self, snowflake: int) -> float:
        """Convert a Discord snowflake to a Unix timestamp (seconds)."""
        return ((snowflake >> 22) + self.DISCORD_EPOCH) / 1000.0

    @staticmethod
    def _sniff_mime(data: bytes) -> str | None:
        """Detect image MIME type from magic bytes."""
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        if data[:3] == b'\xff\xd8\xff':
            return "image/jpeg"
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return "image/webp"
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return "image/gif"
        return None

    def _estimate_image_tokens(self, img_bytes: bytes) -> int:
        """Estimate API token cost for an image.

        Anthropic: tokens = (width * height) / 750
        Falls back to rough estimate from file size if PIL unavailable.
        """
        if HAS_PIL:
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(img_bytes))
                w, h = img.size
                return max(100, (w * h) // 750)
            except Exception:
                pass
        # Rough fallback: typical JPEG is ~10 bytes/pixel,
        # so pixels ≈ size/10, tokens ≈ pixels/750
        return max(100, len(img_bytes) // 7500)

    async def gather_user_context(self, ctx, max_users: int = 2, max_msgs_per_user: int = 1000) -> str:
        """Gather recent messages from mentioned users using local SQLite logs"""
        mentioned = ctx.message.mentions[:max_users]
        if not mentioned:
            return ""

        # Check if Logger cog is available
        if "Logger" not in self.bot.cogs:
            return ""

        logger_cog = self.bot.cogs['Logger']
        db = await logger_cog.get_db(ctx.guild)

        context_parts = []
        for user in mentioned:
            cursor = await db.execute(
                """SELECT u.canon_nick, m.message FROM messages m
                   JOIN users u ON m.user_id = u.user_id
                   WHERE m.user_id = ? AND m.channel_id = ? AND m.message != '' AND m.deleted = 0
                   ORDER BY m.snowflake DESC
                   LIMIT ?""",
                [user.id, ctx.channel.id, max_msgs_per_user]
            )
            rows = await cursor.fetchall()

            if rows:
                # Use canon_nick from DB, rows are (canon_nick, message)
                canon_nick = rows[0][0] or user.display_name
                # Reverse to get chronological order (oldest first)
                msgs = [f"{canon_nick}: {row[1]}" for row in reversed(rows)]
                context_parts.append(f"Recent messages from {canon_nick}:\n" + "\n".join(msgs))
            else:
                context_parts.append(f"No recent messages found for {user.display_name} in this channel.")

        return "\n\n".join(context_parts)

    async def gather_channel_context(self, ctx, hours: int = 24) -> str:
        """Gather recent channel messages from the last N hours using local SQLite logs.

        Includes the bot's own messages tagged with [BOT] prefix for continuity.
        """
        # Check if Logger cog is available
        if "Logger" not in self.bot.cogs:
            return ""

        logger_cog = self.bot.cogs['Logger']
        db = await logger_cog.get_db(ctx.guild)

        # Discord snowflake epoch is 1420070400000 (Jan 1, 2015)
        # Calculate the snowflake for N hours ago
        cutoff_timestamp_ms = (int(time.time()) - (hours * 3600)) * 1000
        cutoff_snowflake = (cutoff_timestamp_ms - 1420070400000) << 22

        bot_user_id = self.bot.user.id

        # Include all messages (including bot's own for continuity)
        cursor = await db.execute(
            """SELECT m.user_id, u.canon_nick, m.message FROM messages m
               JOIN users u ON m.user_id = u.user_id
               WHERE m.channel_id = ? AND m.snowflake > ? AND m.message != ''
               AND m.deleted = 0 AND m.ephemeral = 0
               ORDER BY m.snowflake ASC""",
            [ctx.channel.id, cutoff_snowflake]
        )
        rows = await cursor.fetchall()

        if not rows:
            return ""

        # Include both canon_nick and @mention; tag bot's own messages with [BOT]
        msgs = []
        for row in rows:
            user_id, canon_nick, message = row
            if user_id == bot_user_id:
                msgs.append(f"[BOT] {canon_nick} (<@{user_id}>): {message}")
            else:
                msgs.append(f"{canon_nick} (<@{user_id}>): {message}")

        return "Recent channel conversation:\n" + "\n".join(msgs)

    async def _fetch_messages_range(self, ctx, start_snowflake: int, end_snowflake: int | None = None) -> list:
        """Fetch messages from Logger DB between two snowflakes.

        Returns list of (user_id, canon_nick, message, snowflake) tuples.
        """
        if "Logger" not in self.bot.cogs:
            return []

        logger_cog = self.bot.cogs['Logger']
        db = await logger_cog.get_db(ctx.guild)

        if end_snowflake is not None:
            cursor = await db.execute(
                """SELECT m.user_id, u.canon_nick, m.message, m.snowflake FROM messages m
                   JOIN users u ON m.user_id = u.user_id
                   WHERE m.channel_id = ? AND m.snowflake > ? AND m.snowflake <= ?
                   AND m.message != '' AND m.deleted = 0 AND m.ephemeral = 0
                   ORDER BY m.snowflake ASC""",
                [ctx.channel.id, start_snowflake, end_snowflake],
            )
        else:
            cursor = await db.execute(
                """SELECT m.user_id, u.canon_nick, m.message, m.snowflake FROM messages m
                   JOIN users u ON m.user_id = u.user_id
                   WHERE m.channel_id = ? AND m.snowflake > ?
                   AND m.message != '' AND m.deleted = 0 AND m.ephemeral = 0
                   ORDER BY m.snowflake ASC""",
                [ctx.channel.id, start_snowflake],
            )
        return await cursor.fetchall()

    def _format_messages(self, rows, bot_user_id: int) -> str:
        """Format message rows into text (same format as gather_channel_context)."""
        msgs = []
        for row in rows:
            user_id, canon_nick, message = row[0], row[1], row[2]
            # Strip debug header from bot messages so it doesn't echo back
            if user_id == bot_user_id:
                # Remove debug lines (with or without -# markdown prefix)
                lines = message.split("\n")
                lines = [l for l in lines if not l.lstrip("-# ").startswith("🔧")]
                message = "\n".join(lines)
            if user_id == bot_user_id:
                msgs.append(f"[BOT] {canon_nick} (<@{user_id}>): {message}")
            else:
                msgs.append(f"{canon_nick} (<@{user_id}>): {message}")
        return "\n".join(msgs)

    async def _do_compaction(self, ctx, messages_text: str, compact_max_tokens: int,
                             compact_model: str, token, base_url) -> tuple:
        """Call the compact_model to summarize messages.

        Returns (summary_text, input_tokens, output_tokens) or raises on failure.
        """
        system_prompt = f"""Summarize the following Discord conversation thoroughly. Aim for around {compact_max_tokens} tokens. Preserve:
- Key facts, decisions, and conclusions
- Specific names, numbers, dates, URLs, and technical details
- Important context about users and their preferences
- Any ongoing topics or threads of discussion
- Your own previous responses and positions (marked with [BOT])

Omit:
- Casual greetings, reactions, and small talk
- Redundant back-and-forth
- Messages with no informational value

Be detailed — this summary replaces the original messages and is the only record of what was discussed."""

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": compact_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": messages_text},
            ],
            "max_tokens": compact_max_tokens + 200,  # small buffer
        }

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            async with session.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Compaction API error: {resp.status} - {error_text[:200]}")
                data = await resp.json()

        summary = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", self.provider.estimate_tokens(messages_text))
        output_tokens = usage.get("completion_tokens", self.provider.estimate_tokens(summary))
        cached_tokens = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)

        return summary, input_tokens, output_tokens, cached_tokens

    def _trim_messages_to_budget(self, msgs: list, bot_user_id: int, max_tokens: int) -> list:
        """Trim oldest messages until formatted output fits within max_tokens.

        Uses binary search on message count for efficiency. Applies a 1.2x
        safety margin on token estimates since estimate_tokens (len/4) can
        undercount by 20-30% on code, URLs, or non-English text.
        """
        text = self._format_messages(msgs, bot_user_id)
        if self.provider.estimate_tokens(text) * 1.2 <= max_tokens:
            return msgs

        # Binary search: find minimum messages to drop from front
        lo, hi = 0, len(msgs)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.provider.estimate_tokens(self._format_messages(msgs[mid:], bot_user_id)) * 1.2 <= max_tokens:
                hi = mid
            else:
                lo = mid + 1
        return msgs[lo:]

    async def _build_compacted_context(self, ctx, settings: dict, token, base_url,
                                       compact_model: str = None) -> str:
        """Build context for !clai using compaction.

        Returns the context string (summary + raw messages) to use in the prompt.
        Sets self._last_compaction to 'recompact', 'cold', or None.
        """
        self._last_compaction = None

        bot_user_id = self.bot.user.id
        guild_id = ctx.guild.id
        channel_id = ctx.channel.id

        compact_days = settings["compact_days"]
        raw_hours = settings["raw_hours"]
        raw_max_tokens = settings.get("raw_max_tokens", 5000)
        compact_max_tokens = settings["compact_max_tokens"]
        recompact_raw_tokens = settings["recompact_raw_tokens"]
        if not compact_model:
            compact_model = settings["compact_model"]

        # Use provider-specific context limits if available, otherwise fall back to settings
        MAX_CONTEXT_TOKENS = getattr(self.provider, 'max_context_tokens', None) or settings.get("max_context_tokens", 20000)
        MAX_COMPACTION_INPUT = getattr(self.provider, 'max_compaction_input', None) or settings.get("max_compaction_input", 120000)

        now = time.time()
        compact_window_start = self._ts_to_snowflake(now - compact_days * 86400)
        raw_window_start = self._ts_to_snowflake(now - raw_hours * 3600)

        cache = await self.ai_cache.get_cache(channel_id)

        if cache is not None:
            # ── Warm cache ──
            newest_snowflake = cache["newest_snowflake"]
            # Raw window stretches back to compaction boundary (never gaps)
            raw_msgs = await self._fetch_messages_range(ctx, newest_snowflake)
            # Trim raw messages to token budget
            raw_msgs = self._trim_messages_to_budget(raw_msgs, bot_user_id, raw_max_tokens)
            raw_text = self._format_messages(raw_msgs, bot_user_id)
            raw_tokens = self.provider.estimate_tokens(raw_text)

            # Check re-compaction trigger — token-only, no time component.
            # Only count tokens BEYOND the configured raw_hours window — the raw
            # window always stretches back to the compaction boundary, so in a busy
            # channel it can be large even right after compaction ran.
            overflow_msgs = [m for m in raw_msgs if m[3] <= raw_window_start]
            overflow_tokens = self.provider.estimate_tokens(self._format_messages(overflow_msgs, bot_user_id)) if overflow_msgs else 0
            self._overflow_tokens = overflow_tokens
            self._recompact_threshold = recompact_raw_tokens
            # Recompact when overflow exceeds the token threshold
            needs_recompact = overflow_tokens > recompact_raw_tokens

            if needs_recompact:
                # Full re-summarization
                try:
                    all_msgs = await self._fetch_messages_range(ctx, compact_window_start)
                    if not all_msgs:
                        return raw_text

                    # Split: older portion for compaction, recent for raw
                    older_msgs = [m for m in all_msgs if m[3] <= raw_window_start]
                    recent_msgs = self._trim_messages_to_budget(
                        [m for m in all_msgs if m[3] > raw_window_start], bot_user_id, raw_max_tokens)

                    if not older_msgs:
                        # Nothing old enough to compact
                        return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)

                    older_text = self._format_messages(older_msgs, bot_user_id)

                    # Truncate older text if it exceeds compaction model's context limit
                    if self.provider.estimate_tokens(older_text) > MAX_COMPACTION_INPUT:
                        older_msgs = self._trim_messages_to_budget(older_msgs, bot_user_id, MAX_COMPACTION_INPUT)
                        older_text = self._format_messages(older_msgs, bot_user_id)

                    if self.provider.estimate_tokens(older_text) < compact_max_tokens:
                        # Too small to bother compacting
                        return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)

                    summary, in_tok, out_tok, cached_comp = await self._do_compaction(
                        ctx, older_text, compact_max_tokens, compact_model, token, base_url)
                    self._last_compaction = 'recompact'
                    # Log compaction usage
                    await self.ai_cache.log_usage(
                        channel_id, guild_id, "compaction",
                        in_tok, out_tok, compact_model,
                        cached_tokens=cached_comp)

                    # Update cache
                    newest_older = older_msgs[-1][3]
                    oldest_older = older_msgs[0][3]
                    await self.ai_cache.set_cache(
                        channel_id, guild_id, oldest_older, newest_older,
                        summary, compact_model)

                    recent_text = self._format_messages(recent_msgs, bot_user_id)
                    parts = [f"[Conversation summary — last {compact_days} days]\n{summary}"]
                    if recent_text:
                        parts.append(f"Recent channel conversation:\n{recent_text}")
                    return "\n\n".join(parts)

                except Exception as e:
                    # Keep old cache, skip re-compaction this round
                    self.bot.logger.error(f"Re-compaction failed for #{ctx.channel.name}: {e}")
                    summary = cache["summary_text"]
                    parts = [f"[Conversation summary]\n{summary}"]
                    if raw_text:
                        parts.append(f"Recent channel conversation:\n{raw_text}")
                    return "\n\n".join(parts)

            else:
                # Warm cache, no re-compaction needed
                summary = cache["summary_text"]

                parts = [f"[Conversation summary]\n{summary}"]
                if raw_text:
                    parts.append(f"Recent channel conversation:\n{raw_text}")
                return "\n\n".join(parts)

        else:
            # ── Cold cache ──
            all_msgs = await self._fetch_messages_range(ctx, compact_window_start)
            if not all_msgs:
                return ""

            all_text = self._format_messages(all_msgs, bot_user_id)

            if self.provider.estimate_tokens(all_text) < compact_max_tokens:
                # Small enough, no compaction needed
                return "Recent channel conversation:\n" + all_text

            # Split for compaction
            older_msgs = [m for m in all_msgs if m[3] <= raw_window_start]
            recent_msgs = self._trim_messages_to_budget(
                [m for m in all_msgs if m[3] > raw_window_start], bot_user_id, raw_max_tokens)

            if not older_msgs:
                # Truncate if needed
                all_msgs = self._trim_messages_to_budget(all_msgs, bot_user_id, MAX_CONTEXT_TOKENS)
                return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)

            older_text = self._format_messages(older_msgs, bot_user_id)

            # Truncate older text if it exceeds compaction model's context limit
            if self.provider.estimate_tokens(older_text) > MAX_COMPACTION_INPUT:
                older_msgs = self._trim_messages_to_budget(older_msgs, bot_user_id, MAX_COMPACTION_INPUT)
                older_text = self._format_messages(older_msgs, bot_user_id)

            if self.provider.estimate_tokens(older_text) < compact_max_tokens:
                # Older portion is small, just send everything raw (truncated if needed)
                all_msgs = self._trim_messages_to_budget(all_msgs, bot_user_id, MAX_CONTEXT_TOKENS)
                return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)

            try:
                summary, in_tok, out_tok, cached_comp = await self._do_compaction(
                    ctx, older_text, compact_max_tokens, compact_model, token, base_url)
                self._last_compaction = 'cold'
                # Log compaction
                await self.ai_cache.log_usage(
                    channel_id, guild_id, "compaction",
                    in_tok, out_tok, compact_model,
                    cached_tokens=cached_comp)

                # Store cache
                newest_older = older_msgs[-1][3]
                oldest_older = older_msgs[0][3]
                await self.ai_cache.set_cache(
                    channel_id, guild_id, oldest_older, newest_older,
                    summary, compact_model)

                recent_text = self._format_messages(recent_msgs, bot_user_id)
                parts = [f"[Conversation summary — last {compact_days} days]\n{summary}"]
                if recent_text:
                    parts.append(f"Recent channel conversation:\n{recent_text}")
                return "\n\n".join(parts)

            except Exception as e:
                # Cold start failure — just use raw messages, truncated to fit
                self.bot.logger.error(f"Cold compaction failed for #{ctx.channel.name}: {e}")
                all_msgs = self._trim_messages_to_budget(all_msgs, bot_user_id, MAX_CONTEXT_TOKENS)
                return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)

    async def build_full_context(self, ctx, settings: dict, token: str, base_url: str,
                                compact_model: str = None) -> dict:
        """Build complete context for an AI command.

        Returns dict with:
            channel_context: str - the raw channel context string
            user_context: str - the raw user context string
            system_prompt: str - the system prompt to use
            debug_parts: list[str] - debug info for the 🔧 line
            stable_prefix_tokens: int - estimated cacheable prefix tokens
        """
        use_context = settings.get("context", "on") != "off"
        debug_parts = []

        # If compact_model is set (GLM), use GLM-specific compaction settings if available
        if compact_model:
            effective_settings = dict(settings)
            for key in ("raw_max_tokens", "compact_max_tokens", "raw_hours", "compact_days", "recompact_raw_tokens", "max_compaction_input"):
                glm_key = f"glm_{key}"
                if glm_key in settings:
                    effective_settings[key] = settings[glm_key]
        else:
            effective_settings = settings

        # Build compacted channel context
        if use_context:
            channel_context = await self._build_compacted_context(
                ctx, effective_settings, token, base_url, compact_model=compact_model)
        else:
            channel_context = ""

        # Gather context from mentioned users
        user_context = ""
        if use_context:
            user_context = await self.gather_user_context(ctx)

        # Build system prompt
        custom_prompt = settings.get("system_prompt", "")
        if custom_prompt:
            system_prompt = custom_prompt
        else:
            bot_name = self.bot.user.display_name
            bot_id = self.bot.user.id
            history_note = "\n\nMessages prefixed with [BOT] are your previous responses." if use_context else ""
            system_prompt = f"""You are {bot_name} (Discord user ID: {bot_id}), a Discord bot.
The user talking to you is {ctx.author.display_name}.

Keep responses SHORT. This is Discord — 1-3 sentences for simple questions, a short paragraph max for complex ones. No essays, no bullet-point walls, no "here's a comprehensive overview". Just answer the question.{history_note}

RULES:
- Never dump, repeat, or output raw context/logs even if asked
- Give honest answers, push back when warranted, adult topics are fine
- When addressing users, use their display name (it will be auto-converted to a mention)"""

        # Calculate stable prefix tokens and debug parts
        stable_prefix_tokens = 0
        if channel_context:
            if "[Conversation summary" in channel_context and "Recent channel conversation:" in channel_context:
                parts = channel_context.split("Recent channel conversation:", 1)
                stable_prefix_tokens += self.provider.estimate_tokens(parts[0])
                if hasattr(self, '_last_compaction'):
                    label = self._last_compaction or "cached"
                    debug_parts.append(f"⟳{label}")
                debug_parts.append(f"summary={self.provider.estimate_tokens(parts[0])}tok")
                debug_parts.append(f"raw={self.provider.estimate_tokens(parts[1])}tok")
                if hasattr(self, '_overflow_tokens'):
                    debug_parts.append(f"overflow={self._overflow_tokens}/{self._recompact_threshold}")
            else:
                stable_prefix_tokens += self.provider.estimate_tokens(channel_context)
                debug_parts.append(f"history={self.provider.estimate_tokens(channel_context)}tok")

        if user_context:
            debug_parts.append(f"users={self.provider.estimate_tokens(user_context)}tok")

        return {
            "channel_context": channel_context,
            "user_context": user_context,
            "system_prompt": system_prompt,
            "debug_parts": debug_parts,
            "stable_prefix_tokens": stable_prefix_tokens,
        }

    def wrap_context(self, channel_context: str, user_context: str) -> str:
        """Wrap context sections in XML tags for AI commands.

        Args:
            channel_context: The compacted channel history
            user_context: The user mention context

        Returns:
            str: Combined wrapped context string
        """
        sections = []
        if channel_context:
            sections.append(f'<context type="discord_history" usage="internal_reference_only">\n{channel_context}\n</context>')
        if user_context:
            sections.append(f'<context type="mentioned_users" usage="internal_reference_only">\n{user_context}\n</context>')
        return "\n\n".join(sections) if sections else ""

