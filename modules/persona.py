"""Dynamic persona commands — !clai-<name> that emulates a Discord user's voice.

Admin-only creation/deletion via !claipersona. Personas pull chat logs at
invocation time and instruct the LLM to match the user's communication style.
"""

import re
import time
from datetime import datetime

from discord.ext import commands

from modules.ai_cache import AICache


BOT_ADMIN_ROLE = "Bot Admin"

# ~4 chars per token rough estimate
CHARS_PER_TOKEN = 4

PERSONA_SYSTEM_PROMPT = """You ARE {display_name} in a Discord chat. Not roleplaying — you ARE them.

LENGTH IS CRITICAL: Look at the samples below. Count the words per message. Most Discord users write 1-2 sentences MAX. Match that EXACTLY. If their average message is 8 words, yours should be 8 words. NEVER write paragraphs.

Study the samples for:
- Message LENGTH (this is the #1 priority — match it exactly)
- Slang, emoji, profanity FREQUENCY (don't exaggerate)
- What they DON'T say — if they never use emoji, neither do you
- Energy level — if they're chill, be chill

RULES:
- Do NOT be a caricature. Subtle > obvious.
- Do NOT increase the frequency of any verbal tic.
- Do NOT be more articulate or verbose than the samples show.
- If they'd give a one-word answer, give a one-word answer.
- NEVER write more than 2-3 sentences unless their samples consistently do.
- Never reference that you're an AI.

=== {display_name}'s MESSAGES ({message_count} samples) ===
{voice_sample}
=== END SAMPLES ===""".strip()


async def _check_bot_admin(ctx) -> bool:
    if await ctx.bot.is_owner(ctx.author):
        return True
    return any(role.name == BOT_ADMIN_ROLE for role in ctx.author.roles)


class Persona(commands.Cog):
    """Dynamic persona commands that emulate Discord users."""

    DISCORD_EPOCH = 1420070400000

    def __init__(self, bot):
        self.bot = bot
        self.ai_cache = AICache()
        self._persona_commands = {}  # guild_id -> {name: command}

    async def cog_load(self):
        """Ensure DB is ready on startup."""
        await self._ensure_persona_table()

    def cog_unload(self):
        # Remove all dynamic commands
        for guild_commands in self._persona_commands.values():
            for name, cmd in guild_commands.items():
                self.bot.remove_command(f"clai-{name}")

    async def _ensure_persona_table(self):
        """Create the personas table if it doesn't exist."""
        db = await self.ai_cache.get_db()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS personas (
                guild_id INTEGER NOT NULL,
                persona_name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                sample_tokens INTEGER DEFAULT 50000,
                provider TEXT DEFAULT 'copilot',
                created_by INTEGER NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (guild_id, persona_name)
            )
        """)
        await db.commit()

    async def _get_personas(self, guild_id: int) -> list:
        """Get all personas for a guild."""
        await self._ensure_persona_table()
        db = await self.ai_cache.get_db()
        cursor = await db.execute(
            "SELECT persona_name, user_id, sample_tokens, provider, created_by, created_at "
            "FROM personas WHERE guild_id = ? ORDER BY persona_name",
            [guild_id])
        rows = await cursor.fetchall()
        return [{"name": r[0], "user_id": r[1], "sample_tokens": r[2],
                 "provider": r[3], "created_by": r[4], "created_at": r[5]} for r in rows]

    async def _get_persona(self, guild_id: int, name: str) -> dict | None:
        """Get a single persona by name."""
        await self._ensure_persona_table()
        db = await self.ai_cache.get_db()
        cursor = await db.execute(
            "SELECT persona_name, user_id, sample_tokens, provider, created_by, created_at "
            "FROM personas WHERE guild_id = ? AND persona_name = ?",
            [guild_id, name.lower()])
        row = await cursor.fetchone()
        if not row:
            return None
        return {"name": row[0], "user_id": row[1], "sample_tokens": row[2],
                "provider": row[3], "created_by": row[4], "created_at": row[5]}

    async def _create_persona(self, guild_id: int, name: str, user_id: int,
                               created_by: int, sample_tokens: int = 50000,
                               provider: str = "copilot"):
        """Create or update a persona."""
        await self._ensure_persona_table()
        db = await self.ai_cache.get_db()
        await db.execute(
            "INSERT OR REPLACE INTO personas "
            "(guild_id, persona_name, user_id, sample_tokens, provider, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [guild_id, name.lower(), user_id, sample_tokens, provider, created_by, time.time()])
        await db.commit()

    async def _delete_persona(self, guild_id: int, name: str):
        """Delete a persona."""
        await self._ensure_persona_table()
        db = await self.ai_cache.get_db()
        await db.execute(
            "DELETE FROM personas WHERE guild_id = ? AND persona_name = ?",
            [guild_id, name.lower()])
        await db.commit()

    async def _get_voice_sample(self, guild, user_id: int, target_tokens: int = 50000) -> tuple[str, int]:
        """Pull a user's messages from Logger DB across ALL channels in the guild.

        Returns (formatted_sample, message_count).
        """
        if "Logger" not in self.bot.cogs:
            return "", 0

        logger_cog = self.bot.cogs['Logger']
        db = await logger_cog.get_db(guild)

        target_chars = target_tokens * CHARS_PER_TOKEN

        # Pull messages across all channels, newest first
        cursor = await db.execute(
            """SELECT u.canon_nick, m.message, m.channel_id FROM messages m
               JOIN users u ON m.user_id = u.user_id
               WHERE m.user_id = ? AND m.message != '' AND m.deleted = 0 AND m.ephemeral = 0
               AND m.message NOT LIKE '!%'
               ORDER BY m.snowflake DESC""",
            [user_id])
        rows = await cursor.fetchall()

        if not rows:
            return "", 0

        display_name = rows[0][0]
        # Regex to strip Discord custom emoji like <:name:123456> and <a:name:123456>
        custom_emoji_re = re.compile(r'<a?:\w+:\d+>')
        sample_msgs = []
        chars = 0
        for row in rows:
            msg = custom_emoji_re.sub('', row[1]).strip()
            if not msg:
                continue
            if chars + len(msg) > target_chars:
                break
            sample_msgs.append(msg)
            chars += len(msg)

        # Reverse to chronological order
        sample_msgs.reverse()

        # Format: just the messages, one per line — the LLM needs to see raw voice
        formatted = "\n".join(sample_msgs)
        return formatted, len(sample_msgs)

    async def _invoke_persona(self, ctx, persona_name: str, ask: str):
        """Core persona invocation — shared by all dynamic commands."""
        persona = await self._get_persona(ctx.guild.id, persona_name)
        if not persona:
            await ctx.send(f"Persona `{persona_name}` not found.")
            return

        # Get the Copilot cog for providers and context
        copilot = self.bot.cogs.get("Copilot")
        if not copilot:
            await ctx.send("❌ Copilot cog not loaded.")
            return

        async with ctx.channel.typing():
            ask = copilot.context_gatherer.resolve_mentions(ctx, ask)

            settings = await copilot.ai_cache.get_all_settings(ctx.guild.id, ctx.channel.id)
            show_debug = await copilot._should_debug(ctx, settings)
            debug_parts = []
            t0 = time.monotonic()

            # Pick provider
            if persona["provider"] == "glm":
                provider = copilot.glm_provider
                base_url = await copilot.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "glm_base_url")
                api_key = await copilot.ai_cache.get_setting(ctx.guild.id, None, "glm_api_key") or \
                          await copilot.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "glm_api_key")
                model = await copilot.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "glm_model")
                provider.base_url = base_url
                provider.api_key = api_key
                max_output = min(await copilot.ai_cache.get_setting(ctx.guild.id, ctx.channel.id, "glm_max_output_tokens") or 2000, 300)
            else:
                provider = copilot.provider
                try:
                    token, base_url = await copilot.get_provider_auth()
                except Exception as e:
                    await ctx.send(f"Token error: {e}")
                    return
                model = settings["answer_model"]
                max_output = min(settings.get("max_output_tokens", 500), 300)

            # Pull voice sample
            target_user = ctx.guild.get_member(persona["user_id"])
            display_name = target_user.display_name if target_user else f"User#{persona['user_id']}"

            voice_sample, msg_count = await self._get_voice_sample(
                ctx.guild, persona["user_id"], persona["sample_tokens"])

            if not voice_sample:
                await ctx.send(f"No chat history found for {display_name}.")
                return

            voice_tokens = len(voice_sample) // CHARS_PER_TOKEN
            if show_debug:
                debug_parts.append(f"voice={msg_count}msgs(~{voice_tokens}tok)")

            # Build system prompt
            system_prompt = PERSONA_SYSTEM_PROMPT.format(
                display_name=display_name,
                message_count=msg_count,
                voice_sample=voice_sample,
            )

            # Build channel context (recent conversation for continuity)
            use_context = settings.get("context", "on") != "off"
            if use_context:
                raw_hours = settings.get("raw_hours", 24)
                channel_context = await copilot.context_gatherer.gather_channel_context(
                    ctx, hours=raw_hours)
                if channel_context:
                    ask = f"""<channel_context>
{channel_context}
</channel_context>

<user_question>
{ask}
</user_question>"""

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": ask},
                ],
                "max_tokens": max_output,
            }

            try:
                data = await provider.chat(payload)
                elapsed = time.monotonic() - t0

                message = data["choices"][0]["message"]
                response_text = message.get("content") or ""

                if not response_text.strip():
                    return

                usage = data.get("usage", {})
                in_tok = usage.get("prompt_tokens", provider.estimate_tokens(ask + system_prompt))
                out_tok = usage.get("completion_tokens", provider.estimate_tokens(response_text))
                cached_tok = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)

                await copilot.ai_cache.log_usage(
                    ctx.channel.id, ctx.guild.id, f"clai-{persona_name}",
                    in_tok, out_tok, model, cached_tokens=cached_tok)

                if show_debug:
                    cost = provider.calculate_cost(model, in_tok, out_tok, cached_tok)
                    copilot._add_usage_debug(debug_parts, usage, model, cost, elapsed, cached_tok)

            except Exception as e:
                await ctx.send(f"❌ Persona error: {e}")
                self.bot.logger.error(f"Persona {persona_name} error: {e}")
                return

        # Strip any custom emoji the LLM hallucinated (it copies from voice samples)
        output = re.sub(r'<a?:[\w@]+:\d+>', '', response_text).strip()
        output = copilot.context_gatherer.restore_mentions(ctx, output)
        await copilot._send_with_debug(ctx, output, debug_parts, show_debug)

    def _register_persona_command(self, guild_id: int, name: str):
        """Register a dynamic !clai-<name> command."""
        cmd_name = f"clai-{name}"

        # Don't double-register
        if self.bot.get_command(cmd_name):
            return

        async def persona_callback(ctx, *, ask: str):
            await self._invoke_persona(ctx, name, ask)

        # Create the command
        cmd = commands.Command(
            persona_callback,
            name=cmd_name,
            help=f"Chat as {name} (persona)",
        )
        self.bot.add_command(cmd)

        if guild_id not in self._persona_commands:
            self._persona_commands[guild_id] = {}
        self._persona_commands[guild_id][name] = cmd

    def _unregister_persona_command(self, guild_id: int, name: str):
        """Remove a dynamic !clai-<name> command."""
        cmd_name = f"clai-{name}"
        self.bot.remove_command(cmd_name)
        if guild_id in self._persona_commands:
            self._persona_commands[guild_id].pop(name, None)

    @commands.Cog.listener()
    async def on_ready(self):
        """Register all persona commands for all guilds on bot startup."""
        for guild in self.bot.guilds:
            personas = await self._get_personas(guild.id)
            for p in personas:
                self._register_persona_command(guild.id, p["name"])
        if any(self._persona_commands.values()):
            total = sum(len(v) for v in self._persona_commands.values())
            self.bot.logger.info(f"Persona: registered {total} persona commands")

    @commands.command()
    async def claipersona(self, ctx, action: str = None, *, args: str = None):
        """Manage persona commands (Bot Admin only).

        !claipersona create <name> @user [--tokens N] [--provider copilot|glm]
        !claipersona delete <name>
        !claipersona list
        !claipersona info <name>
        """
        if not await _check_bot_admin(ctx):
            await ctx.reply("Bot admin only.")
            return

        if not action or action.lower() == "list":
            personas = await self._get_personas(ctx.guild.id)
            if not personas:
                await ctx.reply("No personas configured. Use `!claipersona create <name> @user`")
                return
            lines = ["**Personas:**"]
            for p in personas:
                member = ctx.guild.get_member(p["user_id"])
                user_label = member.display_name if member else f"ID:{p['user_id']}"
                lines.append(
                    f"  `!clai-{p['name']}` → {user_label} "
                    f"({p['sample_tokens']//1000}K tokens, {p['provider']})")
            await ctx.reply("\n".join(lines))
            return

        action = action.lower()

        if action == "create":
            if not args:
                await ctx.reply("Usage: `!claipersona create <name> @user [--tokens N] [--provider copilot|glm]`")
                return

            parts = args.split()
            name = parts[0].lower().strip()

            # Validate name
            if not re.match(r'^[a-z0-9_-]+$', name):
                await ctx.reply("Persona name must be lowercase alphanumeric, hyphens, or underscores.")
                return

            # Don't allow names that collide with existing commands
            reserved = {"ai", "config", "help", "status", "persona", "reset", "summary"}
            if name in reserved:
                await ctx.reply(f"Name `{name}` is reserved.")
                return

            # Find user mention
            mention_match = re.search(r'<@!?(\d+)>', args)
            if not mention_match:
                await ctx.reply("Must mention a user: `!claipersona create petko @Petko`")
                return

            target_user_id = int(mention_match.group(1))
            target_user = ctx.guild.get_member(target_user_id)
            if not target_user:
                await ctx.reply("User not found in this server.")
                return

            # Parse optional flags
            sample_tokens = 50000
            provider = "copilot"

            tokens_match = re.search(r'--tokens?\s+(\d+)', args)
            if tokens_match:
                sample_tokens = int(tokens_match.group(1))
                sample_tokens = max(5000, min(200000, sample_tokens))

            provider_match = re.search(r'--provider\s+(\w+)', args)
            if provider_match:
                prov = provider_match.group(1).lower()
                if prov in ("copilot", "glm"):
                    provider = prov
                else:
                    await ctx.reply("Provider must be `copilot` or `glm`.")
                    return

            # Create persona
            await self._create_persona(
                ctx.guild.id, name, target_user_id,
                ctx.author.id, sample_tokens, provider)

            # Register the command
            self._register_persona_command(ctx.guild.id, name)

            await ctx.reply(
                f"✅ Created persona `!clai-{name}` → **{target_user.display_name}** "
                f"({sample_tokens//1000}K tokens, {provider})")

        elif action == "delete":
            if not args:
                await ctx.reply("Usage: `!claipersona delete <name>`")
                return

            name = args.strip().lower()
            persona = await self._get_persona(ctx.guild.id, name)
            if not persona:
                await ctx.reply(f"Persona `{name}` not found.")
                return

            self._unregister_persona_command(ctx.guild.id, name)
            await self._delete_persona(ctx.guild.id, name)
            await ctx.reply(f"✅ Deleted persona `!clai-{name}`")

        elif action == "info":
            if not args:
                await ctx.reply("Usage: `!claipersona info <name>`")
                return

            name = args.strip().lower()
            persona = await self._get_persona(ctx.guild.id, name)
            if not persona:
                await ctx.reply(f"Persona `{name}` not found.")
                return

            member = ctx.guild.get_member(persona["user_id"])
            user_label = member.display_name if member else f"ID:{persona['user_id']}"
            creator = ctx.guild.get_member(persona["created_by"])
            creator_label = creator.display_name if creator else f"ID:{persona['created_by']}"

            created_dt = datetime.fromtimestamp(persona["created_at"]).strftime("%Y-%m-%d %H:%M")

            lines = [
                f"**Persona: `!clai-{name}`**",
                f"  Target: {user_label} (<@{persona['user_id']}>)",
                f"  Tokens: {persona['sample_tokens']:,}",
                f"  Provider: {persona['provider']}",
                f"  Created by: {creator_label} on {created_dt}",
            ]

            # Quick sample count check
            voice_sample, msg_count = await self._get_voice_sample(
                ctx.guild, persona["user_id"], persona["sample_tokens"])
            actual_tokens = len(voice_sample) // CHARS_PER_TOKEN
            lines.append(f"  Available: {msg_count} messages (~{actual_tokens:,} tokens)")

            await ctx.reply("\n".join(lines))

        else:
            await ctx.reply("Unknown action. Use `create`, `delete`, `list`, or `info`.")


async def setup(bot):
    await bot.add_cog(Persona(bot))
