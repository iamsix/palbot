import discord
from discord.ext import commands
import asyncio
import random
import re
from urllib.parse import quote as uriquote


FACES = [" ͡° ͜ʖ ͡°", " ͡° ʖ̯ ͡°", " ͠° ͟ʖ ͡°", " ͡ᵔ ͜ʖ ͡ᵔ", " . •́ _ʖ •̀ .", " ఠ ͟ʖ ఠ", " ͡ಠ ʖ̯ ͡ಠ",
         " ಠ ʖ̯ ಠ", " ಠ ͜ʖ ಠ", " ͡• ͜ʖ ͡• ", " ･ิ ͜ʖ ･ิ", " ͡ ͜ʖ ͡ ", "≖ ͜ʖ≖", "ʘ ʖ̯ ʘ", "ʘ ͟ʖ ʘ",
         "ʘ ͜ʖ ʘ", "* ^ ω ^", "´ ∀ ` *", "◕‿◕｡", "≧▽≦", "o^▽^o", "⌒▽⌒", "*⌒―⌒*",
         "・∀・", "´｡• ω •｡`", "￣ω￣", "°ε° ", "o･ω･o", "＠＾◡＾", "*・ω・", "^人^", "o´▽`o",
         "*´▽`*", " ﾟ^∀^ﾟ", " ´ ω ` ", "≧◡≦", "´• ω •`", "⌒ω⌒", "*^‿^*", "◕‿◕", "*≧ω≦*",
         "｡•́‿•̀｡", "ー_ー", "´ー` ", "‘～` ", "　￣д￣", "￣ヘ￣", "￣～￣　", "ˇヘˇ", "︶▽︶", 
         "ツ", " ´ д ` ", "︶︿︶", " ˘ ､ ˘ ", " ˘_˘ ", " ᐛ ", "・_・", "⇀_⇀", "￢_￢" ]
SHRUG = "¯\\\\\_({})\_/¯"


class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='qp')
    async def quickpoll(self, ctx):
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')
        await ctx.message.add_reaction('\N{CROSS MARK}')

    @commands.command()
    async def translate(self, ctx, *, phrase: str):
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl={}&tl={}&dt=t&q={}"
        langs = re.search("(\w{2})-(\w{2})", phrase[0:5])
        if langs:
            sl = langs.group(1)
            tl = langs.group(2)
            phrase = phrase[6:]
        else:
            sl = "auto"
            tl = "en"

        headers = {'User-Agent': "Mozilla/5.0 (X11; CrOS x86_64 12239.19.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.38 Safari/537.36"}
        url = url.format(sl, tl, uriquote(phrase))
        async with self.bot.session.get(url, headers=headers) as resp:
            result = await resp.json()
            await ctx.send("{} ({}): {}".format(result[0][0][1], result[2], result[0][0][0]))


""" 
    @commands.Cog.listener()
    async def on_message(self, message):
        out = ''
        if message.content.startswith('bot '):
            out = f"{message.author.mention}: {self.decider(message.content[4:])}"
        elif "shrug" in message.content:
            out = self.shrug()
        if out:
            await message.channel.send(out)

    def shrug(self):
        return SHRUG.format(random.choice(FACES))

    def decider(self, msg):
        things = re.split(", or |, | or ", msg, flags=re.IGNORECASE)
        if len(things) > 1: 
            return random.choice(things).strip()
 """


def setup(bot):
    bot.add_cog(Chat(bot))