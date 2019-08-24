import discord
from discord.ext import commands
import asyncio
import random
import re
from urllib.parse import quote as uriquote
import sqlite3


FACES = [" ͡° ͜ʖ ͡°", " ͡° ʖ̯ ͡°", " ͠° ͟ʖ ͡°", " ͡ᵔ ͜ʖ ͡ᵔ", " . •́ _ʖ •̀ .", " ఠ ͟ʖ ఠ", " ͡ಠ ʖ̯ ͡ಠ",
         " ಠ ʖ̯ ಠ", " ಠ ͜ʖ ಠ", " ͡• ͜ʖ ͡• ", " ･ิ ͜ʖ ･ิ", " ͡ ͜ʖ ͡ ", "≖ ͜ʖ≖", "ʘ ʖ̯ ʘ", "ʘ ͟ʖ ʘ",
         "ʘ ͜ʖ ʘ", "* ^ ω ^", "´ ∀ ` *", "◕‿◕｡", "≧▽≦", "o^▽^o", "⌒▽⌒", "*⌒―⌒*",
         "・∀・", "´｡• ω •｡`", "￣ω￣", "°ε° ", "o･ω･o", "＠＾◡＾", "*・ω・", "^人^", "o´▽`o",
         "*´▽`*", " ﾟ^∀^ﾟ", " ´ ω ` ", "≧◡≦", "´• ω •`", "⌒ω⌒", "*^‿^*", "◕‿◕", "*≧ω≦*",
         "｡•́‿•̀｡", "ー_ー", "´ー` ", "‘～` ", "　￣д￣", "￣ヘ￣", "￣～￣　", "ˇヘˇ", "︶▽︶", 
         "ツ", " ´ д ` ", "︶︿︶", " ˘ ､ ˘ ", " ˘_˘ ", " ᐛ ", "・_・", "⇀_⇀", "￢_￢" ]
SHRUG = r"¯\\\_({})\_/¯"


class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.custom_command_conn = sqlite3.connect("customcommands.sqlite")
        cursor = self.custom_command_conn.cursor()
        self.custom_command_cursor = cursor
        result = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='commands';").fetchone()
        if not result:
            cursor.execute("CREATE TABLE 'commands' ('cmd' TEXT UNIQUE ON CONFLICT REPLACE, 'output' TEXT, 'owner' TEXT);")
            self.custom_command_conn.commit()

    @commands.command(name='qp')
    async def quickpoll(self, ctx):
        """Add a Checkmark and X to your post for a quick yes-no poll"""
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')
        await ctx.message.add_reaction('\N{CROSS MARK}')

    @commands.command()
    async def translate(self, ctx, *, phrase: str):
        """Translate short phrases using google translate
        Optionally specify language code such as `!translate en-es cat`"""
        
        langs = re.search(r"(\w{2})-(\w{2})", phrase[0:5])
        if langs:
            sl = langs.group(1)
            tl = langs.group(2)
            phrase = phrase[6:]
        else:
            sl = "auto"
            tl = "en"

        url = "https://translate.googleapis.com/translate_a/single"
        params = {'client': 'gtx', 'sl': sl, 'tl': tl, 'dt': 't', "q": uriquote(phrase)}
        ua = "Mozilla/5.0 (X11; CrOS x86_64 12239.19.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.38 Safari/537.36"
        headers = {'User-Agent': ua}
        async with self.bot.session.get(url, headers=headers, params=params) as resp:
            result = await resp.json()
            await ctx.send("{} ({}): {}".format(result[0][0][1], result[2], result[0][0][0]))



    @commands.Cog.listener()
    async def on_message(self, message):
        out = ''
        prefix = self.bot.command_prefix
        if message.content.lower().startswith('bot '):
            out = f"{message.author.mention}: {self.decider(message.content[4:])}"
        elif "shrug" in message.content:
            out = self.shrug()
        elif message.content[:1] in prefix:
            cmd = message.content[1:].split(" ")[0]
            out = await self.custom_command(cmd)
        if out:
            await message.channel.send(out)

    def shrug(self):
        return SHRUG.format(random.choice(FACES))

    @commands.command(name="bot")
    async def decide(self, ctx, *, line:str):
        """Decide things"""
        out = f"{ctx.author.mention}: {self.decider(line)}"
        await ctx.send(out)

    def decider(self, msg):
        things = re.split(", or |, | or ", msg, flags=re.IGNORECASE)
        if len(things) > 1: 
            return random.choice(things).strip()
 
    async def custom_command(self, command):
        c = self.custom_command_cursor
        result = c.execute("SELECT output FROM commands WHERE cmd = (?)", [command.lower()]).fetchone()
        if not result:
            return
        else:
            return result[0].strip()
             


    @commands.command()
    @commands.has_role('Admins')
    async def addcmd(self, ctx, cmd, *, output: str):
        """Adds a custom command to the bot that will output whatever is in the <output> field"""
        #Currently hard insert so can be used to edit too
        owner = str(ctx.author)
        c = self.custom_command_cursor
        conn = self.custom_command_conn
        c.execute("INSERT INTO commands VALUES (?,?,?)", (cmd.lower(), output, owner))
        conn.commit()
            
    @commands.command()
    @commands.has_role('Admins')
    async def delcmd(self, ctx, cmd: str):
        c = self.custom_command_cursor
        conn = self.custom_command_conn
        c.execute("DELETE FROM commands WHERE cmd = (?)", [cmd.lower()])
        conn.commit()

def setup(bot):
    bot.add_cog(Chat(bot))
