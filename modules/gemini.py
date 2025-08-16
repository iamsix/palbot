# import google.generativeai as genai
from google import genai
from google.genai.types import HarmCategory, HarmBlockThreshold, GenerateContentConfig, ThinkingConfig, Tool, GoogleSearch
import asyncio
from discord.ext import commands
import discord
import pickle
import os.path

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
        self.listeners = allowed_channels.copy()
        # for testing for now...
        self.listeners.remove(1337293879153791036)
        self.last_stats = {}

        genai.Client(api_key=self.bot.config.gemini_key)
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
                client = genai.Client(api_key=self.bot.config.gemini_key)
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

    @commands.command()
    async def sai(self, ctx, *, ask: str):
        """Ask "smart" gemini a question. It uses google and is better for current event questions."""
        client = genai.Client(api_key=self.bot.config.gemini_key)
        grounding_tool = Tool(
            google_search=GoogleSearch()
        )
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=ask,
            config=GenerateContentConfig(
#                max_output_tokens=5000,
                tools=[grounding_tool],
                system_instruction="Give very curt brief answers under 1 paragraph.",
#                thinking_config=ThinkingConfig(thinking_budget=0)
            ),
        )
        await ctx.send(response.text)


    @commands.command()
    async def ai(self, ctx, *, ask: str):
        """Ask gemini AI a question"""
        client = genai.Client(api_key=self.bot.config.gemini_key)
#        grounding_tool = Tool(
#            google_search=GoogleSearch()
#        )
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=ask,
            config=GenerateContentConfig(
                max_output_tokens=5000,
#                tools=[grounding_tool],
                system_instruction="Give very curt brief answers under 1 paragraph.",
                thinking_config=ThinkingConfig(thinking_budget=0)
            ),
        )
        await ctx.send(response.text)

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
        client = genai.Client(api_key=self.bot.config.gemini_key)
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
