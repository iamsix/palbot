"""Voice TTS module — monitors a text channel and reads messages aloud in voice.

Commands:
    !tts join [#channel] [voice_channel]  — Join a voice channel, monitor a text channel
    !tts leave                            — Disconnect from voice
    !tts skip                             — Skip current message
    !tts voices                           — List available voices
    !tts voice <name>                     — Set TTS voice
    !tts status                           — Show current status
"""

import asyncio
import io
import logging
import re
import tempfile
import time
from collections import defaultdict

import discord
import edge_tts
from discord.ext import commands

log = logging.getLogger(__name__)

# Default voice per-guild, can be changed with !tts voice
DEFAULT_VOICE = "en-US-GuyNeural"

# Voice pool for per-user assignment — distinct enough to tell apart
VOICE_POOL = [
    "en-US-GuyNeural",           # Male, deep
    "en-US-AriaNeural",          # Female, warm
    "en-US-AndrewNeural",        # Male, casual
    "en-US-JennyNeural",         # Female, clear
    "en-US-EricNeural",          # Male, authoritative
    "en-US-EmmaNeural",          # Female, friendly
    "en-US-ChristopherNeural",   # Male, mature
    "en-US-MichelleNeural",      # Female, professional
    "en-US-BrianNeural",         # Male, natural
    "en-US-AvaNeural",           # Female, expressive
    "en-US-RogerNeural",         # Male, broadcaster
    "en-US-SteffanNeural",       # Male, youthful
    "en-AU-WilliamMultilingualNeural",  # Male, Australian
    "en-GB-RyanNeural",          # Male, British
    "en-IE-ConnorNeural",        # Male, Irish
    "en-CA-LiamNeural",          # Male, Canadian
]

# Max queued messages before we start dropping
MAX_QUEUE_SIZE = 5

# Max message length to TTS (chars) — longer messages get truncated
MAX_MSG_LENGTH = 1500

# Skip URL-only messages
URL_PATTERN = re.compile(r'^https?://\S+$')

# Clean message text for TTS
MENTION_PATTERN = re.compile(r'<@!?(\d+)>')
CHANNEL_MENTION_PATTERN = re.compile(r'<#(\d+)>')
ROLE_MENTION_PATTERN = re.compile(r'<@&(\d+)>')
EMOJI_PATTERN = re.compile(r'<a?:(\w+):\d+>')
SPOILER_PATTERN = re.compile(r'\|\|.*?\|\|')
CODE_BLOCK_PATTERN = re.compile(r'```.*?```', re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r'`[^`]+`')


class VoiceTTS(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        # guild_id -> config dict
        self.guild_config = {}
        # guild_id -> asyncio.Queue
        self.queues = {}
        # guild_id -> asyncio.Task (consumer)
        self.consumers = {}
        # guild_id -> voice name (global override)
        self.voices = defaultdict(lambda: None)
        # guild_id -> {user_id: voice_name}
        self.user_voices = defaultdict(dict)
        # guild_id -> int (next index into VOICE_POOL)
        self.voice_pool_index = defaultdict(int)
        # guild_id -> bool (is currently speaking)
        self.speaking = {}

    def cog_unload(self):
        for task in self.consumers.values():
            task.cancel()

    def _get_voice(self, guild_id: int, user_id: int) -> str:
        """Get the TTS voice for a user. Assigns from pool if new."""
        # Global override takes precedence
        global_voice = self.voices[guild_id]
        if global_voice:
            return global_voice

        # Check if user already has a voice
        user_map = self.user_voices[guild_id]
        if user_id in user_map:
            return user_map[user_id]

        # Assign next voice from pool
        idx = self.voice_pool_index[guild_id]
        voice = VOICE_POOL[idx % len(VOICE_POOL)]
        user_map[user_id] = voice
        self.voice_pool_index[guild_id] = idx + 1
        return voice

    def _clean_text(self, message: discord.Message) -> str:
        """Clean message content for TTS readability."""
        text = message.content

        # Skip URL-only messages
        if URL_PATTERN.match(text.strip()):
            return ""

        # Replace spoilers
        text = SPOILER_PATTERN.sub("spoiler", text)

        # Remove code blocks
        text = CODE_BLOCK_PATTERN.sub("code block", text)
        text = INLINE_CODE_PATTERN.sub("code", text)

        # Strip URLs from mixed messages (keep surrounding text)
        text = re.sub(r'https?://\S+', '', text)

        # Strip bot debug lines (🔧 ... | ... | ...)
        text = re.sub(r'🔧[^\n]*', '', text)

        # Strip markdown formatting
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)      # italic
        text = re.sub(r'__(.+?)__', r'\1', text)       # underline
        text = re.sub(r'~~(.+?)~~', r'\1', text)       # strikethrough
        text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)  # block quotes

        # Replace user mentions with display names
        def replace_mention(m):
            uid = int(m.group(1))
            member = message.guild.get_member(uid)
            return member.display_name if member else "someone"
        text = MENTION_PATTERN.sub(replace_mention, text)

        # Replace channel mentions
        def replace_channel(m):
            cid = int(m.group(1))
            ch = message.guild.get_channel(cid)
            return ch.name if ch else "a channel"
        text = CHANNEL_MENTION_PATTERN.sub(replace_channel, text)

        # Replace role mentions
        def replace_role(m):
            rid = int(m.group(1))
            role = message.guild.get_role(rid)
            return role.name if role else "a role"
        text = ROLE_MENTION_PATTERN.sub(replace_role, text)

        # Strip custom Discord emoji entirely
        text = EMOJI_PATTERN.sub('', text)

        # Strip remaining Discord markdown artifacts
        text = re.sub(r'[*_~`|>]', '', text)

        # Strip ALL unicode emoji (covers every emoji, not just a hardcoded list)
        text = re.sub(
            r'[\U0001F600-\U0001F64F'   # emoticons
            r'\U0001F300-\U0001F5FF'     # symbols & pictographs
            r'\U0001F680-\U0001F6FF'     # transport & map
            r'\U0001F700-\U0001F77F'     # alchemical
            r'\U0001F780-\U0001F7FF'     # geometric shapes ext
            r'\U0001F800-\U0001F8FF'     # supplemental arrows
            r'\U0001F900-\U0001F9FF'     # supplemental symbols
            r'\U0001FA00-\U0001FA6F'     # chess symbols
            r'\U0001FA70-\U0001FAFF'     # symbols ext-A
            r'\U00002702-\U000027B0'     # dingbats
            r'\U0000FE00-\U0000FE0F'     # variation selectors
            r'\U000024C2-\U0001F251'     # enclosed chars
            r'\U0000200D'                # zero width joiner
            r'\U00002600-\U000026FF'     # misc symbols
            r'\U00002300-\U000023FF'     # misc technical
            r'\U0000203C-\U00003299'     # CJK symbols + misc
            r']+', '', text)

        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Skip if nothing meaningful left (empty, or just a name/mention
        # e.g. bot reposts a Reddit link with just "@user" + embed)
        if not text or len(text.split()) <= 1:
            return ""

        # Truncate
        if len(text) > MAX_MSG_LENGTH:
            text = text[:MAX_MSG_LENGTH] + "... message truncated"

        return text

    async def _generate_tts(self, text: str, voice: str) -> io.BytesIO:
        """Generate TTS audio as MP3 bytes using edge-tts."""
        communicate = edge_tts.Communicate(text, voice)
        audio_data = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.write(chunk["data"])
        audio_data.seek(0)
        return audio_data

    async def _consumer(self, guild_id: int):
        """Process the message queue for a guild, playing TTS one at a time."""
        queue = self.queues[guild_id]
        while True:
            try:
                author_name, text, user_id = await queue.get()
                config = self.guild_config.get(guild_id)
                if not config:
                    continue

                vc: discord.VoiceClient = config.get("voice_client")
                if not vc or not vc.is_connected():
                    continue

                voice = self._get_voice(guild_id, user_id)
                full_text = f"{author_name} says: {text}"

                try:
                    audio_data = await self._generate_tts(full_text, voice)
                except Exception as e:
                    log.error(f"TTS generation failed: {e}")
                    continue

                # Write to temp file (ffmpeg needs seekable input)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp.write(audio_data.read())
                    tmp_path = tmp.name

                try:
                    self.speaking[guild_id] = True
                    source = discord.FFmpegPCMAudio(
                        tmp_path,
                        options="-loglevel quiet"
                    )

                    # Play and wait for completion
                    done = asyncio.Event()

                    def after_playing(error):
                        if error:
                            log.error(f"Player error: {error}")
                        self.bot.loop.call_soon_threadsafe(done.set)

                    vc.play(source, after=after_playing)
                    await done.wait()
                finally:
                    self.speaking[guild_id] = False
                    # Clean up temp file
                    try:
                        import os
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            except asyncio.CancelledError:
                return
            except Exception as e:
                log.error(f"Voice TTS consumer error: {e}")
                await asyncio.sleep(1)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages in monitored channels."""
        # All messages get TTS'd, including bot responses
        if not message.guild:
            return

        guild_id = message.guild.id
        config = self.guild_config.get(guild_id)
        if not config:
            return

        # Check if this is the monitored channel
        if message.channel.id != config.get("text_channel_id"):
            return

        text = self._clean_text(message)
        if not text:
            return

        queue = self.queues.get(guild_id)
        if not queue:
            return

        # Drop if queue is full
        if queue.qsize() >= MAX_QUEUE_SIZE:
            log.warning(f"TTS queue full for guild {guild_id}, dropping message from {message.author}")
            return

        author_name = message.author.display_name
        await queue.put((author_name, text, message.author.id))

    @commands.group(name="tts", invoke_without_command=True)
    async def tts_group(self, ctx):
        """Voice TTS commands. Use !tts join to start."""
        await ctx.send(
            "**Voice TTS Commands:**\n"
            "`!tts join [#text-channel] [voice-channel-name]` — Start TTS\n"
            "`!tts leave` — Disconnect\n"
            "`!tts skip` — Skip current message\n"
            "`!tts voice <name>` — Force one voice for all\n"
            "`!tts voice auto` — Per-user voices (default)\n"
            "`!tts voices` — List voices\n"
            "`!tts status` — Show status + voice assignments"
        )

    @tts_group.command(name="join")
    async def tts_join(self, ctx, text_channel: discord.TextChannel = None,
                       *, voice_channel_name: str = None):
        """Join a voice channel and monitor a text channel for TTS.

        Usage:
            !tts join                          — Monitor current channel, join your VC
            !tts join #palship                 — Monitor #palship, join your VC
            !tts join #palship General Voice   — Monitor #palship, join "General Voice"
        """
        guild_id = ctx.guild.id

        # Determine text channel to monitor
        if text_channel is None:
            text_channel = ctx.channel

        # Determine voice channel to join
        voice_channel = None
        if voice_channel_name:
            # Find by name
            voice_channel = discord.utils.get(
                ctx.guild.voice_channels, name=voice_channel_name
            )
            if not voice_channel:
                # Fuzzy match
                voice_channel_name_lower = voice_channel_name.lower()
                for vc in ctx.guild.voice_channels:
                    if voice_channel_name_lower in vc.name.lower():
                        voice_channel = vc
                        break
            if not voice_channel:
                return await ctx.send(f"Couldn't find voice channel: `{voice_channel_name}`")
        else:
            # Join the user's current voice channel
            if ctx.author.voice and ctx.author.voice.channel:
                voice_channel = ctx.author.voice.channel
            else:
                return await ctx.send("Join a voice channel first, or specify one: `!tts join #channel Voice Channel`")

        # Disconnect existing connection if any
        if guild_id in self.guild_config:
            old_vc = self.guild_config[guild_id].get("voice_client")
            if old_vc and old_vc.is_connected():
                await old_vc.disconnect()
            if guild_id in self.consumers:
                self.consumers[guild_id].cancel()

        # Connect to voice
        try:
            vc = await voice_channel.connect()
        except Exception as e:
            return await ctx.send(f"Failed to connect: {e}")

        # Set up queue and consumer
        self.queues[guild_id] = asyncio.Queue()
        self.guild_config[guild_id] = {
            "voice_client": vc,
            "text_channel_id": text_channel.id,
            "text_channel_name": text_channel.name,
            "voice_channel_name": voice_channel.name,
        }
        self.speaking[guild_id] = False
        self.consumers[guild_id] = self.bot.loop.create_task(self._consumer(guild_id))

        await ctx.send(
            f"🔊 Joined **{voice_channel.name}** — reading **#{text_channel.name}** aloud\n"
            f"Each chatter gets a unique voice. Use `!tts voice <name>` to force one voice for all.\n"
            f"Use `!tts leave` to disconnect"
        )

    @tts_group.command(name="leave")
    async def tts_leave(self, ctx):
        """Disconnect from voice and stop TTS."""
        guild_id = ctx.guild.id
        config = self.guild_config.pop(guild_id, None)
        if not config:
            return await ctx.send("Not connected to any voice channel.")

        # Cancel consumer
        if guild_id in self.consumers:
            self.consumers[guild_id].cancel()
            del self.consumers[guild_id]

        # Clear queue
        if guild_id in self.queues:
            del self.queues[guild_id]

        # Disconnect
        vc = config.get("voice_client")
        if vc and vc.is_connected():
            vc.stop()
            await vc.disconnect()

        self.speaking.pop(guild_id, None)
        await ctx.send("👋 Disconnected from voice. TTS stopped.")

    @tts_group.command(name="skip")
    async def tts_skip(self, ctx):
        """Skip the currently playing TTS message."""
        guild_id = ctx.guild.id
        config = self.guild_config.get(guild_id)
        if not config:
            return await ctx.send("Not connected.")

        vc = config.get("voice_client")
        if vc and vc.is_playing():
            vc.stop()
            await ctx.send("⏭️ Skipped")
        else:
            await ctx.send("Nothing playing.")

    @tts_group.command(name="voice")
    async def tts_voice(self, ctx, *, voice_name: str):
        """Set a global voice override (all users same voice), or 'auto' for per-user voices."""
        guild_id = ctx.guild.id

        if voice_name.lower() == "auto":
            self.voices[guild_id] = None
            self.user_voices[guild_id].clear()
            self.voice_pool_index[guild_id] = 0
            return await ctx.send("🗣️ Switched to **auto** — each chatter gets a unique voice")

        # Validate voice exists
        try:
            voices = await edge_tts.list_voices()
        except Exception as e:
            return await ctx.send(f"Failed to fetch voices: {e}")

        # Exact match
        match = None
        for v in voices:
            if v["ShortName"].lower() == voice_name.lower():
                match = v
                break

        # Partial match
        if not match:
            voice_name_lower = voice_name.lower()
            for v in voices:
                if voice_name_lower in v["ShortName"].lower():
                    match = v
                    break

        if not match:
            return await ctx.send(f"Voice `{voice_name}` not found. Use `!tts voices` to list options.")

        self.voices[guild_id] = match["ShortName"]
        await ctx.send(f"🗣️ Global voice set to **{match['ShortName']}** ({match['Gender']}, {match['Locale']})\nUse `!tts voice auto` to go back to per-user voices")

    @tts_group.command(name="voices")
    async def tts_voices(self, ctx, locale: str = "en"):
        """List available TTS voices. Optionally filter by locale (default: en)."""
        try:
            voices = await edge_tts.list_voices()
        except Exception as e:
            return await ctx.send(f"Failed to fetch voices: {e}")

        filtered = [v for v in voices if v["Locale"].lower().startswith(locale.lower())]
        if not filtered:
            return await ctx.send(f"No voices found for locale `{locale}`")

        lines = []
        current_global = self.voices.get(ctx.guild.id)
        for v in filtered[:30]:
            marker = " 👈" if v["ShortName"] == current_global else ""
            lines.append(f"`{v['ShortName']}` — {v['Gender']}{marker}")

        output = f"**Available voices ({locale}):**\n" + "\n".join(lines)
        if len(filtered) > 30:
            output += f"\n... and {len(filtered) - 30} more"
        output += f"\n\nSet with: `!tts voice <name>`"

        # Split if too long
        if len(output) > 2000:
            for i in range(0, len(output), 1990):
                await ctx.send(output[i:i+1990])
        else:
            await ctx.send(output)

    @tts_group.command(name="status")
    async def tts_status(self, ctx):
        """Show current TTS status."""
        guild_id = ctx.guild.id
        config = self.guild_config.get(guild_id)
        if not config:
            return await ctx.send("Not connected. Use `!tts join` to start.")

        vc = config.get("voice_client")
        connected = vc and vc.is_connected()
        queue = self.queues.get(guild_id)
        queue_size = queue.qsize() if queue else 0
        is_speaking = self.speaking.get(guild_id, False)

        global_voice = self.voices.get(guild_id)
        if global_voice:
            voice_info = f"🗣️ Voice: `{global_voice}` (global override)"
        else:
            user_map = self.user_voices.get(guild_id, {})
            if user_map:
                assignments = []
                for uid, voice in user_map.items():
                    member = ctx.guild.get_member(uid)
                    name = member.display_name if member else str(uid)
                    assignments.append(f"  {name} → `{voice}`")
                voice_info = "🗣️ Per-user voices:\n" + "\n".join(assignments)
            else:
                voice_info = "🗣️ Per-user voices (auto-assigned)"

        status = (
            f"**Voice TTS Status**\n"
            f"🔊 Voice channel: **{config.get('voice_channel_name', '?')}** ({'connected' if connected else 'disconnected'})\n"
            f"📝 Text channel: **#{config.get('text_channel_name', '?')}**\n"
            f"{voice_info}\n"
            f"{'🔈 Currently speaking' if is_speaking else '🔇 Idle'}\n"
            f"📋 Queue: {queue_size}/{MAX_QUEUE_SIZE} messages"
        )
        await ctx.send(status)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Auto-disconnect if everyone leaves the voice channel."""
        if member.bot:
            return

        guild_id = member.guild.id
        config = self.guild_config.get(guild_id)
        if not config:
            return

        vc = config.get("voice_client")
        if not vc or not vc.is_connected():
            return

        # Check if we're alone (only bot left)
        voice_channel = vc.channel
        non_bot_members = [m for m in voice_channel.members if not m.bot]
        if not non_bot_members:
            log.info(f"Everyone left {voice_channel.name}, auto-disconnecting TTS")
            # Clean up
            self.guild_config.pop(guild_id, None)
            if guild_id in self.consumers:
                self.consumers[guild_id].cancel()
                del self.consumers[guild_id]
            if guild_id in self.queues:
                del self.queues[guild_id]
            self.speaking.pop(guild_id, None)
            vc.stop()
            await vc.disconnect()


async def setup(bot):
    await bot.add_cog(VoiceTTS(bot))
