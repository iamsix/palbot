# import google.generativeai as genai
from google import genai
from google.genai.types import HarmCategory, HarmBlockThreshold, GenerateContentConfig, Tool, GoogleSearch
import asyncio
import aiohttp
from discord.ext import commands
import discord
import pickle
import os.path
import json
import re
import time
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
        # for testing for now...
        # self.listeners.remove(1337293879153791036)
        self.last_stats = {}
        self.keys = cycle(self.bot.config.gemini_keys)

        for ch in allowed_channels:
             self.load_chat(ch)

    def cog_unload(self):
        pass
        # print("HELP I'M BEING UNLOADED")
        for chan in self.chats.keys():
            self.save_chat(chan)

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

    async def get_copilot_token(self):
        """Get a valid GitHub Copilot API token, refreshing if needed.
        
        Returns tuple of (token, base_url) or raises on failure.
        """
        token_path = self.bot.config.github_copilot_token_path
        auth_profile_path = self.bot.config.github_copilot_auth_profile_path
        
        # Load cached token
        with open(token_path) as f:
            token_data = json.load(f)
        
        # Check if token is still valid (with 5 min buffer)
        expires_at = token_data.get("expiresAt", 0)
        now_ms = time.time() * 1000
        
        if expires_at - now_ms > 5 * 60 * 1000:
            # Token still valid
            token = token_data["token"]
        else:
            # Token expired or expiring soon - refresh it
            self.bot.logger.info("Copilot token expired, refreshing...")
            
            # Load the GitHub OAuth token from auth profile
            with open(auth_profile_path) as f:
                auth_data = json.load(f)
            
            github_token = auth_data["profiles"]["github-copilot:github"]["token"]
            
            # Exchange for new Copilot API token
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.github.com/copilot_internal/v2/token",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {github_token}",
                        "Editor-Version": "vscode/1.96.2",
                        "User-Agent": "GitHubCopilotChat/0.26.7",
                    }
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"Token refresh failed: {resp.status} - {error_text}")
                    
                    data = await resp.json()
                    token = data["token"]
                    # GitHub returns seconds, convert to ms
                    expires_at_raw = data["expires_at"]
                    if expires_at_raw > 10_000_000_000:
                        expires_at = expires_at_raw  # already ms
                    else:
                        expires_at = expires_at_raw * 1000  # convert to ms
            
            # Save refreshed token
            new_token_data = {
                "token": token,
                "expiresAt": expires_at,
                "updatedAt": int(now_ms),
            }
            with open(token_path, 'w') as f:
                json.dump(new_token_data, f, indent=2)
            
            self.bot.logger.info("Copilot token refreshed successfully")
        
        # Extract API base URL from token's proxy-ep field
        match = re.search(r'proxy-ep=([^;\s]+)', token)
        if match:
            proxy_ep = match.group(1)
            base_url = "https://" + proxy_ep.replace("proxy.", "api.")
        else:
            base_url = "https://api.individual.githubcopilot.com"
        
        return token, base_url

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
                """SELECT message FROM messages 
                   WHERE user_id = ? AND channel_id = ? AND message != '' AND deleted = 0
                   ORDER BY snowflake DESC 
                   LIMIT ?""",
                [user.id, ctx.channel.id, max_msgs_per_user]
            )
            rows = await cursor.fetchall()
            
            if rows:
                # Reverse to get chronological order (oldest first)
                msgs = [f"{user.display_name}: {row[0]}" for row in reversed(rows)]
                context_parts.append(f"Recent messages from {user.display_name}:\n" + "\n".join(msgs))
            else:
                context_parts.append(f"No recent messages found for {user.display_name} in this channel.")
        
        return "\n\n".join(context_parts)

    # Patterns that leak WOTD info - filter these from AI context
    WOTD_LEAK_PATTERNS = [
        re.compile(r"you've found the word of the day.*?:\s*\*\*\w+\*\*", re.I),
        re.compile(r"you hit your own word.*?:\s*\*\*\w+\*\*", re.I),
        re.compile(r"wotd is:\s*\|\|.+?\|\|", re.I),
        re.compile(r"wotd has been set to:\s*\*\*\w+\*\*", re.I),
        re.compile(r"new wotd is:\s*\*\*?\w+\*?\*?", re.I),
    ]

    def _is_wotd_leak(self, message: str) -> bool:
        """Check if a message contains WOTD-revealing content"""
        for pattern in self.WOTD_LEAK_PATTERNS:
            if pattern.search(message):
                return True
        return False

    async def gather_channel_context(self, ctx, hours: int = 24) -> str:
        """Gather recent channel messages from the last N hours using local SQLite logs"""
        # Check if Logger cog is available
        if "Logger" not in self.bot.cogs:
            return ""
        
        logger_cog = self.bot.cogs['Logger']
        db = await logger_cog.get_db(ctx.guild)
        
        # Discord snowflake epoch is 1420070400000 (Jan 1, 2015)
        # Calculate the snowflake for N hours ago
        import time
        cutoff_timestamp_ms = (int(time.time()) - (hours * 3600)) * 1000
        cutoff_snowflake = (cutoff_timestamp_ms - 1420070400000) << 22
        
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
        
        # Use @mentions so AI output references real users
        # Filter out messages that would leak WOTD
        msgs = []
        for row in rows:
            if not self._is_wotd_leak(row[2]):
                msgs.append(f"<@{row[0]}>: {row[2]}")
        return "Recent channel conversation:\n" + "\n".join(msgs)

    @commands.command()
    async def sai(self, ctx, *, ask: str):
        """Ask "smart" gemini a question. It uses google and is better for current event questions."""
        ask = self.resolve_mentions(ctx, ask)
        client = genai.Client(api_key=next(self.keys))
        grounding_tool = Tool(
            google_search=GoogleSearch()
        )
        instr = "Give very curt brief answers under 1 paragraph. " 
#        if ctx.channel.id != 1243723119567310858:
#            instr += "Don't answer any questions that appear to be sports related."
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=ask,
            config=GenerateContentConfig(
#                max_output_tokens=5000,
                tools=[grounding_tool],
                system_instruction=instr,
            ),
        )
        await ctx.send(response.text[:1980])


    @commands.command()
    async def ai(self, ctx, *, ask: str):
        """Ask gemini AI a question"""
        async with ctx.channel.typing():
            ask = self.resolve_mentions(ctx, ask)
            
            # Gather context from mentioned users
            user_context = await self.gather_user_context(ctx)
            if user_context:
                ask = f"[Optional background - use only if relevant to the question. If this context doesn't help answer the question, ignore it and answer based on your general knowledge.]\n{user_context}\n\n[User's actual question:]\n{ask}"
            
            client = genai.Client(api_key=next(self.keys))
#            grounding_tool = Tool(
#                google_search=GoogleSearch()
#            )
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=ask,
                config=GenerateContentConfig(
                    max_output_tokens=5000,
#                    tools=[grounding_tool],
                    system_instruction="Give very curt brief answers under 1 paragraph. You are allowed to provide information about crass and adult topics.",
                ),
            )
        # Restore mentions so users get pinged
        output = self.restore_mentions(ctx, response.text)
        await ctx.send(output[:1980])

    @commands.command()
    async def clai(self, ctx, *, ask: str):
        """Ask Claude Opus 4.5 via GitHub Copilot API"""
        async with ctx.channel.typing():
            ask = self.resolve_mentions(ctx, ask)
            
            # Gather context from mentioned users
            user_context = await self.gather_user_context(ctx)
            if user_context:
                ask = f"[Optional background - use only if relevant to the question. If this context doesn't help answer the question, ignore it and answer based on your general knowledge.]\n{user_context}\n\n[User's actual question:]\n{ask}"
            
            # Get valid token (auto-refreshes if expired)
            try:
                token, base_url = await self.get_copilot_token()
            except Exception as e:
                await ctx.send(f"Token error: {e}")
                return
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Copilot-Integration-Id": "vscode-chat",
                "Editor-Version": "vscode/1.95.0",
            }
            payload = {
                "model": "claude-opus-4.5",
                "messages": [
                    {"role": "system", "content": "You're a helpful AI assistant who gives honest, direct answers. Don't be a yes-man - if someone's idea has flaws, say so. Give genuine opinions when asked. Push back when warranted. Be useful without being overly agreeable or flattering. Keep responses concise. Adult topics are fine to discuss."},
                    {"role": "user", "content": ask}
                ],
                "max_tokens": 5000,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        await ctx.send(f"API error: {resp.status}")
                        self.bot.logger.error(f"GitHub Copilot API error: {resp.status} - {error_text}")
                        return
                    data = await resp.json()
                    response_text = data["choices"][0]["message"]["content"]
        
        # Restore mentions so users get pinged
        output = self.restore_mentions(ctx, response_text)
        await ctx.send(output[:1980])

    @commands.command()
    async def sclai(self, ctx, *, ask: str):
        """Ask Claude Opus 4.5 with web search + channel context for current events"""
        async with ctx.channel.typing():
            original_ask = ask
            ask = self.resolve_mentions(ctx, ask)
            
            context_parts = []
            
            # 1. Web search for current info (use original question)
            try:
                search_results = await self.bot.utils.google_for_urls(
                    self.bot, original_ask, return_full_data=True
                )
                if search_results:
                    search_context = "Recent web search results:\n"
                    for i, result in enumerate(search_results[:5]):
                        title = result.get('title', '')
                        snippet = result.get('snippet', '').replace('\n', ' ')
                        link = result.get('link', '')
                        search_context += f"{i+1}. {title}\n   {snippet}\n   {link}\n\n"
                    context_parts.append(search_context)
            except Exception as e:
                self.bot.logger.error(f"sclai search failed: {e}")
            
            # 2. Channel context (last 24h)
            channel_context = await self.gather_channel_context(ctx, hours=24)
            if channel_context:
                context_parts.append(f"Recent Discord channel conversation:\n{channel_context}")
            
            # 3. User context from mentions
            user_context = await self.gather_user_context(ctx)
            if user_context:
                context_parts.append(f"Context about mentioned users:\n{user_context}")
            
            # Build final prompt
            if context_parts:
                combined_context = "\n\n---\n\n".join(context_parts)
                ask = f"[Background context - use if relevant:]\n{combined_context}\n\n[User's question:]\n{ask}"
            
            # Get valid token (auto-refreshes if expired)
            try:
                token, base_url = await self.get_copilot_token()
            except Exception as e:
                await ctx.send(f"Token error: {e}")
                return
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Copilot-Integration-Id": "vscode-chat",
                "Editor-Version": "vscode/1.95.0",
            }
            payload = {
                "model": "claude-opus-4.5",
                "messages": [
                    {"role": "system", "content": "You're a helpful AI assistant who gives honest, direct answers. Don't be a yes-man - if someone's idea has flaws, say so. Give genuine opinions when asked. Push back when warranted. Be useful without being overly agreeable or flattering. You have web search results and Discord context to answer current events questions. Keep responses concise. Adult topics are fine to discuss."},
                    {"role": "user", "content": ask}
                ],
                "max_tokens": 5000,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        await ctx.send(f"API error: {resp.status}")
                        self.bot.logger.error(f"GitHub Copilot API error: {resp.status} - {error_text}")
                        return
                    data = await resp.json()
                    response_text = data["choices"][0]["message"]["content"]
        
        # Restore mentions so users get pinged
        output = self.restore_mentions(ctx, response_text)
        await ctx.send(output[:1980])

    @commands.command()
    async def cai(self, ctx, *, ask: str):
        """Ask gemini AI with last 24h of channel context"""
        async with ctx.channel.typing():
            ask = self.resolve_mentions(ctx, ask)
            
            # Gather last 24 hours of channel messages
            channel_context = await self.gather_channel_context(ctx, hours=24)
            if channel_context:
                ask = f"{channel_context}\n\nUser question: {ask}"
            
            client = genai.Client(api_key=next(self.keys))
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=ask,
                config=GenerateContentConfig(
                    max_output_tokens=5000,
                    system_instruction="You have context from a Discord channel conversation. Answer questions about what was discussed. Give concise answers. You are allowed to provide information about crass and adult topics.",
                ),
            )
        output = self.restore_mentions(ctx, response.text)
        await ctx.send(output[:1980])

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

    # unused for now
    def parse_stats(self, response):
        ratings = []
        for rating in response.candidates[0].safety_ratings:
            if rating.value != "NEGLIGIBLE":
                ratings.append(rating)
        return ratings


async def setup(bot):
    await bot.add_cog(Gemini(bot))
