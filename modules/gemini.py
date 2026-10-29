# import google.generativeai as genai
from google import genai
from google.genai.types import HarmCategory, HarmBlockThreshold, GenerateContentConfig, Tool, GoogleSearch
import asyncio
import aiosqlite
from discord.ext import commands
import discord
import pickle
import os.path
from itertools import cycle

# https://discordpy.readthedocs.io/en/stable/api.html#thread
# look in to threads/parent channel
# If threads are good allow !newchat Directives in a thread that doesn't have one (this starts one)

# reset chat for reusing threads???
# if so need a way to archive old model pickle version

# on thread creation method?

# parse safety ratings?
# if so ignore negligible and maybe Low

# change these to a bot config probably. Will need to change the chat_channel check for that.
BOT_ADMIN_ROLE = "Bot Admin"
DEFAULT_SAI_COOLDOWN_LIMIT = 3
DEFAULT_SAI_COOLDOWN_TIME = 900
DEFAULT_SYSTEM_INSTRUCTION = (
    "You are a curt, direct assistant. "
    "Answer the user's question in 1 or 2 short sentences maximum. "
    "Never write a full paragraph or list details. Do not repeat yourself."
)

def is_bot_admin():
    """Check: bot owner OR has the Bot Admin role."""
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        return any(role.name == BOT_ADMIN_ROLE for role in ctx.author.roles)
    return commands.check(predicate)


allowed_channels = [985728639981211728, 1333677981322969149, 1337293879153791036]


SAFETY = [
    {
        "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
    # Add other categories if your specific model supports them
   # {
   #      "category": HarmCategory.HARM_CATEGORY_TOXICITY,
   #      "threshold": HarmBlockThreshold.BLOCK_NONE,
   #  },
   #  {
   #      "category": HarmCategory.HARM_CATEGORY_VIOLENCE,
   #      "threshold": HarmBlockThreshold.BLOCK_NONE,
   #  },
   #  {
   #      "category": HarmCategory.HARM_CATEGORY_DEROGATORY,
   #      "threshold": HarmBlockThreshold.BLOCK_NONE,
   #  },
]

class Gemini(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.chats = {}
        self.listeners = []
        self.sai_cooldown_pending = {}
        self.sai_cooldowns = {}
        # for testing for now...
        # self.listeners.remove(1337293879153791036)
        self.last_stats = {}
        self.keys = cycle(self.bot.config.gemini_keys)
        self._settings_db = None

        for ch in allowed_channels:
             self.load_chat(ch)

    def cog_unload(self):
        # print("HELP I'M BEING UNLOADED")
        for chan in self.chats.keys():
            self.save_chat(chan)
        if self._settings_db:
            asyncio.ensure_future(self._settings_db.close())

    async def _ensure_settings_db(self):
        """Lazily initialize the settings database."""
        if self._settings_db is not None:
            return
        self._settings_db = await aiosqlite.connect("data/gemini_settings.sqlite")
        instruction_default = DEFAULT_SYSTEM_INSTRUCTION.replace("'", "''")
        await self._settings_db.execute(
            "CREATE TABLE IF NOT EXISTS settings ("
            "  guild_id INTEGER NOT NULL,"
            "  channel_id INTEGER NOT NULL,"
            "  enabled TEXT NOT NULL DEFAULT 'on',"
            f"  cooldown_limit INTEGER NOT NULL DEFAULT {DEFAULT_SAI_COOLDOWN_LIMIT},"
            f"  cooldown_time INTEGER NOT NULL DEFAULT {DEFAULT_SAI_COOLDOWN_TIME},"
            f"  system_instruction TEXT NOT NULL DEFAULT '{instruction_default}',"
            "  PRIMARY KEY (guild_id, channel_id)"
            ")"
        )
        async with self._settings_db.execute("PRAGMA table_info(settings)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        migrations = (
            (
                "cooldown_limit",
                f"INTEGER NOT NULL DEFAULT {DEFAULT_SAI_COOLDOWN_LIMIT}",
            ),
            (
                "cooldown_time",
                f"INTEGER NOT NULL DEFAULT {DEFAULT_SAI_COOLDOWN_TIME}",
            ),
            (
                "system_instruction",
                f"TEXT NOT NULL DEFAULT '{instruction_default}'",
            ),
        )
        for column, definition in migrations:
            if column not in columns:
                await self._settings_db.execute(
                    f"ALTER TABLE settings ADD COLUMN {column} {definition}"
                )
        await self._settings_db.commit()

    async def _get_channel_settings(self, guild_id: int, channel_id: int):
        """Get channel settings, applying defaults when no row exists."""
        await self._ensure_settings_db()
        async with self._settings_db.execute(
            "SELECT enabled, cooldown_limit, cooldown_time, system_instruction "
            "FROM settings WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return {
                "enabled": True,
                "cooldown_limit": DEFAULT_SAI_COOLDOWN_LIMIT,
                "cooldown_time": DEFAULT_SAI_COOLDOWN_TIME,
                "system_instruction": DEFAULT_SYSTEM_INSTRUCTION,
            }
        return {
            "enabled": row[0] != "off",
            "cooldown_limit": row[1],
            "cooldown_time": row[2],
            "system_instruction": row[3] or DEFAULT_SYSTEM_INSTRUCTION,
        }

    async def _is_enabled(self, guild_id: int, channel_id: int) -> bool:
        """Check if !ai/!sai are enabled in a channel."""
        settings = await self._get_channel_settings(guild_id, channel_id)
        return settings["enabled"]

    async def _set_enabled(self, guild_id: int, channel_id: int, value: str):
        """Set the enabled state for a channel."""
        await self._ensure_settings_db()
        await self._settings_db.execute(
            "INSERT INTO settings (guild_id, channel_id, enabled) VALUES (?, ?, ?)"
            " ON CONFLICT(guild_id, channel_id) DO UPDATE SET enabled = excluded.enabled",
            (guild_id, channel_id, value),
        )
        await self._settings_db.commit()

    async def _set_config_value(
        self, guild_id: int, channel_id: int, key: str, value: int | str
    ):
        """Persist a validated channel setting."""
        columns = {
            "cooldown_limit",
            "cooldown_time",
            "system_instruction",
        }
        if key not in columns:
            raise ValueError(f"Unsupported AI setting: {key}")
        await self._ensure_settings_db()
        await self._settings_db.execute(
            f"INSERT INTO settings (guild_id, channel_id, {key}) VALUES (?, ?, ?)"
            f" ON CONFLICT(guild_id, channel_id) DO UPDATE SET {key} = excluded.{key}",
            (guild_id, channel_id, value),
        )
        await self._settings_db.commit()

    @staticmethod
    def _format_cooldown_time(seconds: int) -> str:
        if seconds % 3600 == 0:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''}"
        if seconds % 60 == 0:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        return f"{seconds} second{'s' if seconds != 1 else ''}"

    @staticmethod
    async def _send_long_text(ctx, text: str):
        for start in range(0, len(text), 1900):
            await ctx.send(text[start:start + 1900])

    def save_chat(self, channel: int):
        # I can't pickle the entire chat[channel] object due to an active connection
        #  so I just pickle the important parts
        with open(f'logfiles/gemini_{channel}.pkl', 'wb') as fp:
            
            obj = {"channel": channel,
                "model": self.chats[channel]._model,
                "instructions": self.chats[channel]._config.system_instruction,
                "history": self.chats[channel].get_history(),
            }
            pickle.dump(obj, fp, -1)

    def load_chat(self, channel: int):
        # Since we only pickled the components we have to make a 'new' chat with the same
        #  instructions and history
        if os.path.isfile(f'logfiles/gemini_{channel}.pkl'):
            with open(f'logfiles/gemini_{channel}.pkl', 'rb') as fp:
                obj = pickle.load(fp)
                client = genai.Client(api_key=next(self.keys))
                chat_session = client.aio.chats.create(
                    model=obj['model'],
                    history=obj['history'],
                    config=GenerateContentConfig(
                        system_instruction=obj['instructions']
                    ),
                )
                self.chats[channel] = chat_session
                
                return True
        else:
            return False

    async def chat_channel(ctx, silent = False):
        if ctx.invoked_with == "help":
            return True
        if isinstance(ctx.channel, discord.Thread) and ctx.channel.parent.id in allowed_channels:
            return True
        if  (ctx.guild and ctx.guild.id == 124572142485504002) and ctx.channel.id not in allowed_channels:
            # print("HERE")
            if not silent:
                msg = await ctx.reply(f"`chat only works in <#985728639981211728>. This message will self destruct.")
                await asyncio.sleep(5)
                await msg.delete()
            return False
        else:
            return True
            
        
#    async def cog_command_error(self, ctx, error):
#        if isinstance(error, commands.errors.CheckFailure):
#            return
#        else:
#            print(error)

    def resolve_mentions(self, ctx, text: str) -> str:
        """Replace Discord mention IDs with display names"""
        for user in ctx.message.mentions:
            text = text.replace(f'<@{user.id}>', user.display_name)
            text = text.replace(f'<@!{user.id}>', user.display_name)
        return text

    def restore_mentions(self, ctx, text: str) -> str:
        """Replace display names back to Discord mentions in output"""
        for user in ctx.message.mentions:
            text = text.replace(user.display_name, f'<@{user.id}>')
        return text

    @commands.command()
    async def sai(self, ctx, *, ask: str):
        """Ask "smart" gemini a question. It uses google and is better for current event questions."""
        settings = (
            await self._get_channel_settings(ctx.guild.id, ctx.channel.id)
            if ctx.guild
            else {
                "enabled": True,
                "cooldown_limit": DEFAULT_SAI_COOLDOWN_LIMIT,
                "cooldown_time": DEFAULT_SAI_COOLDOWN_TIME,
                "system_instruction": DEFAULT_SYSTEM_INSTRUCTION,
            }
        )
        if not settings["enabled"]:
            return
        channel_id = ctx.channel.id
        limit = settings["cooldown_limit"]
        cooldown_time = settings["cooldown_time"]
        cooldown = self.sai_cooldowns.get(channel_id)
        if cooldown is None or cooldown[:2] != (limit, cooldown_time):
            mapping = commands.CooldownMapping.from_cooldown(
                limit, cooldown_time, commands.BucketType.user
            )
            cooldown = (limit, cooldown_time, mapping)
            self.sai_cooldowns[channel_id] = cooldown
        bucket = cooldown[2].get_bucket(ctx.message)
        user_id = ctx.author.id
        pending_key = (channel_id, user_id)
        pending = self.sai_cooldown_pending.get(pending_key, 0)
        if bucket.get_tokens() <= pending:
            retry_after = bucket.get_retry_after()
            if retry_after:
                message = (
                    f"You can use this command {limit} times per "
                    f"{self._format_cooldown_time(cooldown_time)}. "
                    f"Try again in about {int(retry_after) + 1} seconds."
                )
            else:
                message = (
                    f"All {limit} request slots are currently in use. "
                    "Try again shortly."
                )
            await ctx.send(message)
            return

        self.sai_cooldown_pending[pending_key] = pending + 1
        succeeded = False
        try:
            async with ctx.channel.typing():
                ask = self.resolve_mentions(ctx, ask)
                try:
                    client = genai.Client(api_key=next(self.keys))
                    grounding_tool = Tool(
                        google_search=GoogleSearch()
                    )
                    response = await client.aio.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=ask,
                        config=GenerateContentConfig(
                            tools=[grounding_tool],
                            system_instruction=settings["system_instruction"],
                        ),
                    )

                    candidate = response.candidates[0]
                    if candidate.finish_reason != "STOP":
                        await ctx.send(
                            f"Warning: Model finished with reason: {candidate.finish_reason}"
                        )
                    await ctx.send(response.text[:1980])
                    succeeded = True
                except Exception as e:
                    error_msg = str(e)
                    await ctx.send(f"❌ API error: {error_msg[:100]}")
                    self.bot.logger.error(f"!sai error: {e}")
        finally:
            pending = self.sai_cooldown_pending[pending_key] - 1
            if pending:
                self.sai_cooldown_pending[pending_key] = pending
            else:
                del self.sai_cooldown_pending[pending_key]
            if succeeded:
                bucket.update_rate_limit()


    @commands.command()
    async def ai(self, ctx, *, ask: str):
        """Ask gemini AI a question"""
        await self.sai(ctx, ask=ask)

    @commands.command(hidden=True)
    async def dbgchat(self, ctx):
        for key, chat in self.chats.items():
            print(type(chat))


#     @commands.command(hidden=True)
#     @commands.is_owner()
#     async def specialchat(self, ctx):
#         history = []
#         with open(f'logfiles/clean2024.log', 'r') as fp:
#             for line in fp:
#                 history.append({"role": "user", "parts": [{"text": line}]})
#         instr = """You will recieve a discord log in the format of: <@userid:username>: message
#         Input messages and queries will be in the same format - no need to include that format in your own messages or quote the user's id or nick.
# You should analyze this log file and provde information about the users in the log that the other discord users in the chat will ask you about.
# """
#         model = genai.GenerativeModel(
#                 model_name="gemini-2.0-flash",
#                 system_instruction=instr
#         )
#         self.chats[ctx.channel.id] = model.start_chat(history=history)
# #        self.listeners.append(ctx.channel.id)
#         await ctx.send("OK. The special chat is initiated, and you can now ask questions about the discord log from early 2024")

    @commands.check(chat_channel)
    @commands.command()
    async def newchat(self, ctx, *, instructions: str = ""):
        """Creates a gemini chat bot instance for a chat thread"""
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.send("This can only be done in a Thread of this channel")
            return
        
        if ctx.author.id != ctx.channel.owner.id:
            await ctx.send("You're not the owner of this thread. Only the thread maker can do that")
            return
        
        instr = "You are in a discord, all input messages will be in the format of '<@userid:username> message', you don't need to include your nick in the output. "
        client = genai.Client(api_key=next(self.keys))
        chat_session = client.aio.chats.create(
            model="gemini-2.5-flash",
            config=GenerateContentConfig(
                system_instruction=instr + instructions
            ),
        )
        self.chats[ctx.channel.id] = chat_session


    async def resetchat(self, ctx):
        # this one will reset with the same params but no history
        pass

    @commands.command(hidden=True)
    async def listenall(self, ctx):
        chan = ctx.channel.id
        if not await Gemini.chat_channel(ctx, True):
            return   
        # if chan not in self.chats:
        #     await ctx.send("I don't see an active chat here to listen to messages for...")
        #     return

        if chan not in self.listeners:
            self.listeners.append(chan)
            msg = "OK, I'm currently listening to all messages in the channel"
        else:
            self.listeners.remove(chan)
            msg = "OK, I'll only reply to `!chat` messages specifically"
        await ctx.send(msg)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        chan = message.channel.id
        if chan not in self.listeners or message.author.id == self.bot.user.id:
            return
        # if not await Gemini.chat_channel(message, True):
        #     return
        if message.content.startswith('!') or message.content.startswith('>'):
            return
        
        await self.chat_response(message.content, message)

    
    @commands.check(chat_channel)
    @commands.command(hidden=True)
    async def chat(self, ctx, *, line: str):
        await self.chat_response(line, ctx.message)

    async def chat_response(self, line, message):
        # Right now this part is redundant until I do the thread thing
        if message.channel.id not in self.chats and not self.load_chat(message.channel.id):
            await message.channel.send("Failed to load chat history, probably need to create one")
            return
        async with message.channel.typing():
            msg = f"<@{message.author.id}:{message.author.display_name}> {line}"
            try: 
                response = await self.chats[message.channel.id].send_message(msg)
                # parse safety_ratings instead?
                # self.last_stats[message.channel.id] = 
                self.last_stats[message.channel.id] = f"{response.usage_metadata}\n{response.candidates[0].safety_ratings}"
                for i in range(0, len(response.text), 1970):                
                    await message.reply(response.text[i:i+1970])
            except Exception as e:
                await message.reply(f"Probably a rate limit: {e}")

    @commands.command(hidden=True)
    async def aistats(self, ctx, channel: int = None):
        if not channel:
            await ctx.send(self.last_stats[ctx.channel.id]) 
        else:
            await ctx.send(self.last_stats[channel]) 

    @commands.command()
    @is_bot_admin()
    async def aiconfig(self, ctx, key: str = None, *, value: str = None):
        """Configure !ai and !sai per-channel (Bot Admin only).

        !aiconfig              — show current setting for this channel
        !aiconfig enabled on   — enable !ai and !sai in this channel
        !aiconfig enabled off  — disable !ai and !sai in this channel
        !aiconfig cooldown_limit 5 — set the allowed requests per cooldown
        !aiconfig cooldown_time 600 — set the cooldown duration in seconds
        !aiconfig system_instruction <text> — set the system instruction
        Use `!aiconfig system_instruction default` to restore the default.
        """
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        guild_id = ctx.guild.id
        channel_id = ctx.channel.id

        if key is None:
            settings = await self._get_channel_settings(guild_id, channel_id)
            status = "on" if settings["enabled"] else "off"
            instruction = settings["system_instruction"].replace("\n", " ")
            if len(instruction) > 120:
                instruction = instruction[:117] + "..."
            await ctx.send(
                f"⚙️ **AI Settings** — <#{channel_id}>\n"
                f"  `enabled`: **{status}**\n\n"
                f"  `cooldown_limit`: **{settings['cooldown_limit']}**\n"
                f"  `cooldown_time`: **{settings['cooldown_time']} seconds**\n"
                f"  `system_instruction`: {instruction}\n\n"
                f"Use `!aiconfig <key> <value>` to change a setting."
            )
            return

        if key not in {
            "enabled",
            "cooldown_limit",
            "cooldown_time",
            "system_instruction",
        }:
            await ctx.send(
                f"❌ Unknown setting `{key}`. Available settings: `enabled`, "
                "`cooldown_limit`, `cooldown_time`, `system_instruction`."
            )
            return

        if value is None:
            settings = await self._get_channel_settings(guild_id, channel_id)
            if key == "enabled":
                status = "on" if settings["enabled"] else "off"
                await ctx.send(
                    f"`enabled` is currently **{status}** for <#{channel_id}>.\n"
                    "Use `!aiconfig enabled on` or `!aiconfig enabled off` to change."
                )
            elif key == "system_instruction":
                await self._send_long_text(
                    ctx,
                    f"`system_instruction` for <#{channel_id}>:\n"
                    f"{settings['system_instruction']}"
                )
            else:
                await ctx.send(
                    f"`{key}` is currently **{settings[key]}** for <#{channel_id}>."
                )
            return

        if key == "enabled":
            value = value.strip().lower()
            if value not in ("on", "off"):
                await ctx.send("❌ Value must be `on` or `off`.")
                return
            await self._set_enabled(guild_id, channel_id, value)
            await ctx.send(f"✅ `enabled` set to **{value}** for <#{channel_id}>")
            return

        if key in {"cooldown_limit", "cooldown_time"}:
            try:
                numeric_value = int(value.strip())
            except ValueError:
                await ctx.send(f"❌ `{key}` must be a positive whole number.")
                return
            if numeric_value < 1:
                await ctx.send(f"❌ `{key}` must be at least 1.")
                return
            value = numeric_value
        else:
            value = value.strip()
            if value.lower() == "default":
                value = DEFAULT_SYSTEM_INSTRUCTION
            elif not value:
                await ctx.send(
                    "❌ `system_instruction` cannot be empty. "
                    "Use `default` to restore the default instruction."
                )
                return

        await self._set_config_value(guild_id, channel_id, key, value)
        await ctx.send(f"✅ `{key}` updated for <#{channel_id}>.")

    # unused for now
    def parse_stats(self, response):
        ratings = []
        for rating in response.candidates[0].safety_ratings:
            if rating.value != "NEGLIGIBLE":
                ratings.append(rating)
        return ratings


async def setup(bot):
    await bot.add_cog(Gemini(bot))
