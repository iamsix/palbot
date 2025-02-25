import google.generativeai as genai
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

SAFETY = {
    'HATE': 'BLOCK_NONE',
    'HARASSMENT': 'BLOCK_NONE',
    'SEXUAL' : 'BLOCK_NONE',
    'DANGEROUS' : 'BLOCK_NONE'
}

class Gemini(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.chats = {}
        self.listeners = allowed_channels.copy()
        # for testing for now...
        self.listeners.remove(1337293879153791036)
        self.last_stats = {}

        genai.configure(api_key=self.bot.config.gemini_key)
        for ch in allowed_channels:
            self.load_chat(ch)

    def cog_unload(self):
        # print("HELP I'M BEING UNLOADED")
        for chan in self.chats.keys():
            self.save_chat(chan)

    def save_chat(self, channel: int):
        # I can't pickle the entire chat[channel] object due to an active connection
        #  so I just pickle the important parts
        with open(f'logfiles/gemini_{channel}.pkl', 'wb') as fp:
            
            obj = {"channel": channel,
                "model": self.chats[channel].model.model_name,
                "instructions": self.chats[channel].model._system_instruction.parts[0].text,
                "history": self.chats[channel].history,
            }
            pickle.dump(obj, fp, -1)

    def load_chat(self, channel: int):
        # Since we only pickled the components we have to make a 'new' chat with the same
        #  instructions and history
        if os.path.isfile(f'logfiles/gemini_{channel}.pkl'):
            with open(f'logfiles/gemini_{channel}.pkl', 'rb') as fp:
                obj = pickle.load(fp)
                model = genai.GenerativeModel(
                    model_name=obj['model'],
                    system_instruction=obj['instructions']
                )
                self.chats[channel] = model.start_chat(history=obj['history'])
                
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
    async def ai(self, ctx, *, ask: str):
        genai.configure(api_key=self.bot.config.gemini_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction="Give brief answers of around 1 paragraph"
        )
        response = await model.generate_content_async(
            ask,
            generation_config = genai.GenerationConfig(
                max_output_tokens=200,
            )
        )
        await ctx.send(response.text)

    @commands.command()
    async def dbgchat(self, ctx):
        for key, chat in self.chats.items():
            print(type(chat))


    @commands.command(hidden=True)
    @commands.is_owner()
    async def specialchat(self, ctx):
        history = []
        with open(f'logfiles/clean2024.log', 'r') as fp:
            for line in fp:
                history.append({"role": "user", "parts": [{"text": line}]})
        instr = """You will recieve a discord log in the format of: <@userid:username>: message
        Input messages and queries will be in the same format - no need to include that format in your own messages or quote the user's id or nick.
You should analyze this log file and provde information about the users in the log that the other discord users in the chat will ask you about.
"""
        model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                system_instruction=instr
        )
        self.chats[ctx.channel.id] = model.start_chat(history=history)
#        self.listeners.append(ctx.channel.id)
        await ctx.send("OK. The special chat is initiated, and you can now ask questions about the discord log from early 2024")

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
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=instr + instructions
        )
        self.chats[ctx.channel.id] = model.start_chat()


    async def resetchat(self, ctx):
        # this one will reset with the same params but no history
        pass

    @commands.command()
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
        
        await self.chat_response(message)

    
    @commands.check(chat_channel)
    @commands.command()
    async def chat(self, ctx, *, line: str):
        ctx.message.content = ctx.message.content[6:]
        await self.chat_response(ctx.message)

    async def chat_response(self, message: discord.Message):
        # Right now this part is redundant until I do the thread thing
        if message.channel.id not in self.chats and not self.load_chat(message.channel.id):
            await message.channel.send("Failed to load chat history, probably need to create one")
            return
        async with message.channel.typing():
            msg = f"<@{message.author.id}:{message.author.display_name}> {message.content}"
            response = await self.chats[message.channel.id].send_message_async(
                    msg, 
               #     safety_settings=SAFETY
                    )
            # parse safety_ratings instead?
            # self.last_stats[message.channel.id] = 
            self.last_stats[message.channel.id] = f"{response.usage_metadata}\n{response.candidates[0].safety_ratings}"
            for i in range(0, len(response.text), 1970):                
                await message.reply(response.text[i:i+1970])

    @commands.command()
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
