import google.generativeai as genai
import asyncio
from discord.ext import commands
import discord
import pickle
from io import StringIO
import os.path

# https://discordpy.readthedocs.io/en/stable/api.html#thread
# look in to threads/parent channel
# If threads are good allow !newchat Directives in a thread that doesn't have one (this starts one)

# reset chat for reusing threads???
# if so need a way to archive old model pickle version

# on thread creation method?

# parse safety ratings?
# if so ignore negligible and maybe Low

allowed_channels = [985728639981211728, 1333677981322969149]

class Gemini(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.chats = {}
        self.listeners = allowed_channels.copy()
        self.last_stats = {}
        for ch in allowed_channels:
            self.load_chat(ch)

    def save_chat(self, channel: int):
        # pickle the *entire* Model object, since it will have instructions with it
        with open(f'logfiles/gemini_{channel}.pkl', 'wb') as fp:
            pickle.dump(self.chats[channel], fp, -1)

    def load_chat(self, channel: int):
        if os.path.isfile(f'logfiles/gemini_{channel}.pkl'):
            with open(f'logfiles/gemini_{channel}.pkl', 'rb') as fp:
                self.chats[channel] = pickle.load(fp)
                return True
        else:
            return False

    def cog_unload(self):
        # print("HELP I'M BEING UNLOADED")
        for chan in self.chats.keys():
            self.save_chat(chan)

    async def chat_channel(ctx):
        if  (ctx.guild and ctx.guild.id == 124572142485504002) and ctx.channel.id not in allowed_channels:
            msg = await ctx.reply(f"`chat only works in <#985728639981211728>. This message will self destruct.")
            await asyncio.sleep(5)
            await msg.delete()

            return False
        else:
            return True
        
    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.errors.CheckFailure):
            return
        else:
            print(error)

    @commands.command()
    async def aistats(self, ctx, channel: int = None):
        if not channel:
            await ctx.send(self.last_stats[ctx.channel.id]) 
        else:
            await ctx.send(self.last_stats[channel]) 

    @commands.command()
    async def ai(self, ctx, *, ask: str):
        genai.configure(api_key=self.bot.config.gemini_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash-exp",
            system_instruction="Give brief answers of around 1 paragraph"
        )
        response = await model.generate_content_async(
            ask,
            generation_config = genai.GenerationConfig(
                max_output_tokens=200,
            )
        )
        await ctx.send(response.text)

    def create_chat(self, channel: int, instructions: str):
        #make this a command and use ctx?
        # maybe TextChannel instead of int?
        # check if it's a thread with a whitelisted parent channel
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash-exp",
            system_instruction=instructions
        )
        self.chats[channel] = model.start_chat()

    async def resetchat(self, ctx):
        pass

    @commands.command()
    async def listenall(self, ctx):
        chan = ctx.channel.id
        if chan not in allowed_channels:
            return
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
        if chan not in self.listeners:
            return
        if chan not in allowed_channels or message.author.id == self.bot.user.id:
            return
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
        # if message.channel.id not in self.chats and not self.load_chat(message.channel.id):
        #     await message.channel.send("Failed to load chat history, probably need to create one")
        #     return
        async with message.channel.typing():
            msg = f"<@{message.author.id}:{message.author.display_name}> {message.content}"
            response = await self.chats[message.channel.id].send_message_async(msg)
            # parse safety_ratings instead?
            # self.last_stats[message.channel.id] = 
            self.last_stats[message.channel.id] = f"{response.usage_metadata}\n{response.candidates[0].safety_ratings}"
            for i in range(0, len(response.text), 1970):                
                await message.reply(response.text[i:i+1970])

    # unused for now
    def parse_stats(self, response):
        ratings = []
        for rating in response.candidates[0].safety_ratings:
            if rating.value != "NEGLIGIBLE":
                ratings.append(rating)
        return ratings


async def setup(bot):
    await bot.add_cog(Gemini(bot))
