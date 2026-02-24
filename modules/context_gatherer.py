"""Shared context gathering and compaction logic for AI commands.

Provides reusable methods for:
- Building compacted channel context from Discord logs
- Gathering user context from mentions
- Message fetching and formatting
- Compaction summary caching and rebuilding
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
    """Shared context gathering and compaction utilities for AI commands."""

    DISCORD_EPOCH = 1420070400000  # Jan 1, 2015 in ms

    IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    IMAGE_URL_PATTERN = re.compile(r'https?://\S+', re.IGNORECASE)
    MAX_IMAGE_BYTES = 3_500_000  # ~3.5MB raw; base64 is ~33% larger → ~4.7MB (API limit ~5MB)
    MAX_IMAGE_DIMENSION = 2048   # max width or height in pixels

    def __init__(self, bot, ai_cache: AICache, provider=None):
        self.bot = bot
        self.ai_cache = ai_cache
        self.provider = provider

    @staticmethod
    def resolve_mentions(ctx, text: str) -> str:
        """Replace Discord mention IDs with display names"""
        for user in ctx.message.mentions:
            text = text.replace(f'<@{user.id}>', user.display_name)
            text = text.replace(f'<@!{user.id}>', user.display_name)
        return text

    @staticmethod
    def restore_mentions(ctx, text: str) -> str:
        """Replace display names back to Discord mentions in output"""
        mention_map = {}
        for user in ctx.message.mentions:
            mention_map[user.display_name] = f'<@{user.id}>'
            if hasattr(user, 'name') and user.name != user.display_name:
                mention_map[user.name] = f'<@{user.id}>'
        author = ctx.author
        mention_map[author.display_name] = f'<@{author.id}>'
        if hasattr(author, 'name') and author.name != author.display_name:
            mention_map[author.name] = f'<@{author.id}>'
        for name in sorted(mention_map, key=len, reverse=True):
            text = text.replace(name, mention_map[name])
        return text

    @staticmethod
    def _ts_to_snowflake(timestamp_s: float) -> int:
        """Convert a Unix timestamp (seconds) to a Discord snowflake."""
        return (int(timestamp_s * 1000) - ContextGatherer.DISCORD_EPOCH) << 22

    @staticmethod
    def _snowflake_to_ts(snowflake: int) -> float:
        """Convert a Discord snowflake to a Unix timestamp (seconds)."""
        return ((snowflake >> 22) + ContextGatherer.DISCORD_EPOCH) / 1000.0

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

    @staticmethod
    def _estimate_image_tokens(img_bytes: bytes) -> int:
        """Estimate API token cost for an image."""
        if HAS_PIL:
            try:
                img = Image.open(io.BytesIO(img_bytes))
                w, h = img.size
                return max(100, (w * h) // 750)
            except Exception:
                pass
        return max(100, len(img_bytes) // 7500)

    async def gather_user_context(self, ctx, max_users: int = 2, max_msgs_per_user: int = 1000) -> str:
        """Gather recent messages from mentioned users using local SQLite logs"""
        mentioned = ctx.message.mentions[:max_users]
        if not mentioned:
            return ""

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
                canon_nick = rows[0][0] or user.display_name
                msgs = [f"{canon_nick}: {row[1]}" for row in reversed(rows)]
                context_parts.append(f"Recent messages from {canon_nick}:\n" + "\n".join(msgs))
            else:
                context_parts.append(f"No recent messages found for {user.display_name} in this channel.")

        return "\n\n".join(context_parts)

    async def gather_channel_context(self, ctx, hours: int = 24) -> str:
        """Gather recent channel messages from the last N hours using local SQLite logs.
        Includes the bot's own messages tagged with [BOT] prefix for continuity.
        """
        if "Logger" not in self.bot.cogs:
            return ""

        logger_cog = self.bot.cogs['Logger']
        db = await logger_cog.get_db(ctx.guild)

        cutoff_timestamp_ms = (int(time.time()) - (hours * 3600)) * 1000
        cutoff_snowflake = (cutoff_timestamp_ms - ContextGatherer.DISCORD_EPOCH) << 22
        bot_user_id = self.bot.user.id

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
            if user_id == bot_user_id:
                lines = message.split("\n")
                lines = [l for l in lines if not l.lstrip("-# ").startswith("🔧")]
                message = "\n".join(lines)
            if user_id == bot_user_id:
                msgs.append(f"[BOT] {canon_nick} (<@{user_id}>): {message}")
            else:
                msgs.append(f"{canon_nick} (<@{user_id}>): {message}")
        return "\n".join(msgs)

    async def _do_compaction(self, ctx, messages_text: str, compact_max_tokens: int,
                             compact_model: str, token: str, base_url: str, headers: dict = None) -> tuple:
        """Call the compact_model to summarize messages.

        Returns (summary_text, input_tokens, output_tokens, cached_tokens) or raises on failure.
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

        if headers is None:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Copilot-Integration-Id": "vscode-chat",
                "Editor-Version": "vscode/1.95.0",
            }

        payload = {
            "model": compact_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": messages_text},
            ],
            "max_tokens": compact_max_tokens + 200,
        }

        async with aiohttp.ClientSession() as session:
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
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cached_tokens = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)

        return summary, input_tokens, output_tokens, cached_tokens

    def _trim_messages_to_budget(self, msgs: list, bot_user_id: int, max_tokens: int) -> list:
        """Trim oldest messages until formatted output fits within max_tokens.

        Uses binary search on message count for efficiency. Applies a 1.2x
        safety margin on token estimates since estimate_tokens (len/4) can
        undercount by 20-30% on code, URLs, or non-English text.
        """
        text = self._format_messages(msgs, bot_user_id)
        # Simple token estimation (len/4)
        estimated_tokens = len(text) // 4

        if estimated_tokens * 1.2 <= max_tokens:
            return msgs

        lo, hi = 0, len(msgs)
        while lo < hi:
            mid = (lo + hi) // 2
            test_text = self._format_messages(msgs[mid:], bot_user_id)
            test_tokens = len(test_text) // 4
            if test_tokens * 1.2 <= max_tokens:
                hi = mid
            else:
                lo = mid + 1
        return msgs[lo:]

    async def _build_compacted_context(self, ctx, settings: dict, token: str, base_url: str, headers: dict = None) -> str:
        """Build context for AI commands using compaction.

        Returns the context string (summary + raw messages) to use in the prompt.
        Sets internal attributes for debugging: _last_compaction, _overflow_tokens, _recompact_threshold.
        """
        self._last_compaction = None
        MAX_CONTEXT_TOKENS = 20000
        MAX_COMPACTION_INPUT = 120000

        bot_user_id = self.bot.user.id
        guild_id = ctx.guild.id
        channel_id = ctx.channel.id

        compact_days = settings["compact_days"]
        raw_hours = settings["raw_hours"]
        raw_max_tokens = settings.get("raw_max_tokens", 5000)
        compact_max_tokens = settings["compact_max_tokens"]
        recompact_raw_tokens = settings["recompact_raw_tokens"]
        compact_model = settings["compact_model"]

        now = time.time()
        compact_window_start = self._ts_to_snowflake(now - compact_days * 86400)
        raw_window_start = self._ts_to_snowflake(now - raw_hours * 3600)

        cache = await self.ai_cache.get_cache(channel_id)

        if cache is not None:
            # Warm cache
            newest_snowflake = cache["newest_snowflake"]
            raw_msgs = await self._fetch_messages_range(ctx, newest_snowflake)
            raw_msgs = self._trim_messages_to_budget(raw_msgs, bot_user_id, raw_max_tokens)
            raw_text = self._format_messages(raw_msgs, bot_user_id)

            overflow_msgs = [m for m in raw_msgs if m[3] <= raw_window_start]
            overflow_tokens = self.provider.estimate_tokens(self._format_messages(overflow_msgs, bot_user_id)) if overflow_msgs else 0
            self._overflow_tokens = overflow_tokens
            self._recompact_threshold = recompact_raw_tokens
            needs_recompact = overflow_tokens > recompact_raw_tokens

            if needs_recompact:
                try:
                    all_msgs = await self._fetch_messages_range(ctx, compact_window_start)
                    if not all_msgs:
                        return "Recent channel conversation:\n" + self._format_messages(raw_msgs, bot_user_id)

                    older_msgs = [m for m in all_msgs if m[3] <= raw_window_start]
                    recent_msgs = self._trim_messages_to_budget(
                        [m for m in all_msgs if m[3] > raw_window_start], bot_user_id, raw_max_tokens)

                    if not older_msgs:
                        return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)

                    older_text = self._format_messages(older_msgs, bot_user_id)

                    if self.provider.estimate_tokens(older_text) > MAX_COMPACTION_INPUT:
                        older_msgs = self._trim_messages_to_budget(older_msgs, bot_user_id, MAX_COMPACTION_INPUT)
                        older_text = self._format_messages(older_msgs, bot_user_id)

                    if self.provider.estimate_tokens(older_text) < compact_max_tokens:
                        return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)

                    summary, in_tok, out_tok, cached_comp = await self._do_compaction(
                        ctx, older_text, compact_max_tokens, compact_model, token, base_url, headers)
                    self._last_compaction = 'recompact'
                    await self.ai_cache.log_usage(
                        channel_id, guild_id, "compaction",
                        in_tok, out_tok, compact_model,
                        cached_tokens=cached_comp)

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
                    self.bot.logger.error(f"Re-compaction failed for #{ctx.channel.name}: {e}")
                    summary = cache["summary_text"]
                    parts = [f"[Conversation summary]\n{summary}"]
                    if raw_text:
                        parts.append(f"Recent channel conversation:\n{raw_text}")
                    return "\n\n".join(parts)

            else:
                summary = cache["summary_text"]
                parts = [f"[Conversation summary]\n{summary}"]
                if raw_text:
                    parts.append(f"Recent channel conversation:\n{raw_text}")
                return "\n\n".join(parts)

        else:
            # Cold cache
            all_msgs = await self._fetch_messages_range(ctx, compact_window_start)
            if not all_msgs:
                return ""

            all_text = self._format_messages(all_msgs, bot_user_id)

            if self.provider.estimate_tokens(all_text) < compact_max_tokens:
                all_msgs = self._trim_messages_to_budget(all_msgs, bot_user_id, MAX_CONTEXT_TOKENS)
                return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)

            older_msgs = [m for m in all_msgs if m[3] <= raw_window_start]
            recent_msgs = self._trim_messages_to_budget(
                [m for m in all_msgs if m[3] > raw_window_start], bot_user_id, raw_max_tokens)

            if not older_msgs:
                all_msgs = self._trim_messages_to_budget(all_msgs, bot_user_id, MAX_CONTEXT_TOKENS)
                return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)

            older_text = self._format_messages(older_msgs, bot_user_id)

            if self.provider.estimate_tokens(older_text) > MAX_COMPACTION_INPUT:
                older_msgs = self._trim_messages_to_budget(older_msgs, bot_user_id, MAX_COMPACTION_INPUT)
                older_text = self._format_messages(older_msgs, bot_user_id)

            if self.provider.estimate_tokens(older_text) < compact_max_tokens:
                all_msgs = self._trim_messages_to_budget(all_msgs, bot_user_id, MAX_CONTEXT_TOKENS)
                return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)

            try:
                summary, in_tok, out_tok, cached_comp = await self._do_compaction(
                    ctx, older_text, compact_max_tokens, compact_model, token, base_url, headers)
                self._last_compaction = 'cold'
                await self.ai_cache.log_usage(
                    channel_id, guild_id, "compaction",
                    in_tok, out_tok, compact_model,
                    cached_tokens=cached_comp)

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
                self.bot.logger.error(f"Cold compaction failed for #{ctx.channel.name}: {e}")
                all_msgs = self._trim_messages_to_budget(all_msgs, bot_user_id, MAX_CONTEXT_TOKENS)
                return "Recent channel conversation:\n" + self._format_messages(all_msgs, bot_user_id)
