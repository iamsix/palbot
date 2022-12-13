import discord
from discord.ext import commands
import asyncio
import random
from utils.time import human_timedelta
import sqlite3
import subprocess
from datetime import datetime,timedelta


common_words = ["the", "people", "would", "really", "think", "right", "there", "about", "were", "when", "your", "can",
                "which", "each", "other", "them", "then", "into", "him", "write", "more", "their", "make", "word", "some",
                "many", "time", "look", "see", "who", "may", "down", "get", "day", "come", "part", "like", "now", "these",
                "other", "said", "could", "she"]


# TODO : Count the number of times each user has hit the wotd

class WotdPrompt(discord.ui.Modal, title="Set a new WOTD"):
    new_wotd = discord.ui.TextInput(label="New Word of the Day", min_length=3, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'WOTD has been set to: **{self.new_wotd}** \nIf you want to set a new word before someone finds it use the command `!newwotd` to spawn a new button.', ephemeral=True)

class WotdButton(discord.ui.View):
    message = None
    def __init__(self, wotd, finder) -> None:
        super().__init__(timeout=300)
        self.wotd_finder = finder
        self.new_wotd = ""
        self.wotd = wotd
    @discord.ui.button(label="Set New Word", emoji="\N{MEMO}", style=discord.ButtonStyle.blurple)
    async def on_click_wotd(self, interaction, button):
        if interaction.user.id != self.wotd_finder.id:
            await interaction.response.send_message(f"You didn't find the word", ephemeral=True)
        else:
            modal = WotdPrompt()
            await interaction.response.send_modal(modal)
            await modal.wait()
            self.wotd.bot.logger.info(f"New WOTD is: {modal.new_wotd}")
            self.wotd.wotd = str(modal.new_wotd)
            chan = self.message.channel.id
            self.wotd.single_setter(chan, "setter", self.wotd_finder.id)
            self.wotd.single_setter(chan, "timestamp", str(self.wotd.timestamp))
            self.wotd.single_setter(chan, "wotd", self.wotd.wotd)
            self.wotd.single_setter(chan, "message", self.message.id)
            self.wotd.single_setter(chan, "hint", self.wotd.hint)
            self.stop()
            await self.message.edit(content=self.message.content, view=None)

    async def on_timeout(self):
        self.wotd.wotd = random.choice(common_words)
#        self.wotd.setter = self.wotd.bot.user
        self.wotd.timestamp = datetime.utcnow()
        await self.message.channel.send("New WOTD button has expired, so it has been set to a random common word")
        await self.message.edit(content=self.message.content, view=None)



#This is currently written to assume only 1 channel does WOTD and the word is the same across all servers
# The DB is designed to support multiple channels/servers but code assumes 1 specific channel


class Wotd(commands.Cog):
    wotd = ""
    setter = None
    timestamp = None
    expire_timer = None
    hint = ""

    def __init__(self, bot):
        self.bot = bot
        self.wotd = random.choice(common_words)
        self.setter = bot.user
        self.timestamp = datetime.utcnow()
        self.hint = ""

        self.conn = sqlite3.connect("wotd.sqlite")
        self.c = self.conn.cursor()

        q = "SELECT name FROM sqlite_master WHERE type='table' AND name='settings';"
        result = self.c.execute(q).fetchone()
        if not result:
            q = '''CREATE TABLE 'settings' ("channel" integer, "setting" text, "value" text);'''
            self.c.execute(q)
            self.conn.commit()
        self.bot.loop.create_task(self.load_wotd())

    
    async def load_wotd(self):
        if self.single_getter(self.bot.config.wotd_whitelist[0], "wotd"):
            self.wotd = self.single_getter(self.bot.config.wotd_whitelist[0], "wotd")
            self.hint = self.single_getter(self.bot.config.wotd_whitelist[0], "hint") 
            setterid = self.single_getter(self.bot.config.wotd_whitelist[0], "setter")
            try:
                self.setter = await self.bot.fetch_user(setterid)
            except:
                self.setter = self.bot.user
            ts = self.single_getter(self.bot.config.wotd_whitelist[0], "timestamp")
            self.timestamp = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
            tssec = int((datetime.utcnow() - self.timestamp).total_seconds())
            waittime = 24*60*60 - tssec 
            if waittime < 0:
                #Over 24hrs have elapsed so we're on to 6hr hints
                tssec -= 24*60*60
                waittime = 6*60*60 - (tssec % (6*60*60))
            channel = self.bot.get_channel(self.bot.config.wotd_whitelist[0])
            self.expire_timer = asyncio.ensure_future(self.expire_word(channel, waittime))


    def single_getter(self, channel, key):
        q = '''SELECT value FROM settings WHERE channel = (?) AND setting = (?); '''
        result = self.c.execute(q, (channel, key)).fetchone()
        if result:
            return result[0]
        else:
            return None

    def single_setter(self, channel, key, value):
        q = '''SELECT value FROM settings WHERE channel = (?) AND setting = (?); '''
        result = self.c.execute(q, (channel, key)).fetchone()
        if result:
            q = '''UPDATE settings SET value = (?) WHERE channel = (?) AND setting = (?); '''
            self.c.execute(q, (value, channel, key))
        else:
            q = '''INSERT INTO settings VALUES (?, ?, ?); '''
            self.c.execute(q, (channel, key, value))
        self.conn.commit()


    @commands.command(hidden=True)
    async def newwotd(self, ctx):
        """Lets the WOTD owner set a new word"""
        if ctx.author.id != self.setter.id:
            return

        button = WotdButton(self, ctx.message.author)
        mymsg = await ctx.send("The WOTD owner can set a new WOTD with the button below", view=button)
        button.message = mymsg

    @commands.command(hidden=True)
    @commands.is_owner()
    async def wotdtest(self, ctx):
        """Lets you set a new WOTD for testing.
        Sets WOTD author to the bot so that you can test trigger it"""
        button = WotdButton(self, ctx.message.author)
        mymsg = await ctx.send("What does this do...", view=button)
        button.message = mymsg
        self.setter = self.bot.user
        self.timestamp = datetime.utcnow()

    
    async def expire_word(self, channel, waittime = 24 * 60 * 60):
        self.bot.logger.info(f"waiting {waittime} to expire the word")
        await asyncio.sleep(waittime)
        self.bot.logger.info("Should expire message the word now!")
        hint = ""
        if not self.hint:
            self.hint = "*" * len(self.wotd)
        for i in range(len(self.wotd)):
             # reveal 33% of letters at random
             if self.hint[i] != "*":
                 hint += self.hint[i]
             elif random.choice([True, False, False]):
                 hint += self.wotd[i]
             else:
                 hint += "*"
        self.hint = hint
        self.single_setter(channel.id, "hint", self.hint)
        print("Sending wotd expire message")
        await channel.send(f"The WOTD has been set for >24 hours and no one has found it yet. So here's a hint: `{hint}`")
        print("Sent expire message... setting new timer")
        self.expire_timer = asyncio.ensure_future(self.expire_word(channel, 6*60*60))


    @commands.command(hidden=True)
    @commands.is_owner()
    async def checkwotd(self, ctx):
        """Shows you the current wotd, who set it, and when"""
        ago = human_timedelta(self.timestamp, source=datetime.utcnow(), suffix=True)

        await ctx.send(f"wotd is: ||{self.wotd}|| set by **{self.setter.display_name}** on {self.timestamp} UTC {ago} - hint: `{self.hint}`")


    @commands.command(hidden=True)
    async def wotd(self, ctx):
        """Shows some stats about the current wotd"""
        if not self.wotd:
            return
        ago = human_timedelta(self.timestamp, source=datetime.utcnow(), suffix=True)

        # TODO: move this to a function and calculate it only once
        filename = f'logfiles/{self.bot.config.wotd_whitelist[0]}.log'
        cmd = f'grep -ic {self.wotd} {filename}'
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        wordcount = int(process.communicate(timeout=5)[0][:-1])

        if self.hint:
            hint = f'`{self.hint}` '
        else:
            hint = ""

        await ctx.send(f"The WOTD {hint}was set by **{self.setter.display_name}** {ago}.\nThe word has been used {wordcount} times in this channel")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id not in self.bot.config.wotd_whitelist or \
           message.author.id == self.bot.user.id or \
           " " not in message.content or \
           not self.wotd:
             return

        if self.wotd.lower() in message.content.lower():
            self.expire_timer.cancel()
            ttime = 1
            ago = human_timedelta(self.timestamp, source=datetime.utcnow(), suffix=True)
            button = WotdButton(self, message.author)
            msg = f"Congratulations? You've found the word of the day: **{self.wotd}** that was set by {self.setter.mention} {ago}. Now you can take some time and think about that.\nPlease push the button below to set a new word (after the timeout)."
            if message.author.id == self.setter.id:
                ttime = 2
                msg = f"Wow. You hit your own word: **{self.wotd}** that *you* set {ago}. Now you gotta wait twice as long. You can still set a new word though after the timeout."
            mymsg = await message.reply(msg, view=button)
            button.message = mymsg
            self.wotd = ""
            self.hint = ""
            self.setter = message.author
            self.timestamp = datetime.utcnow()
            self.expire_timer = asyncio.ensure_future(self.expire_word(message.channel))
            try:
                await message.author.timeout(timedelta(minutes=ttime), reason=f"wotd {self.wotd}")
            except Exception as e:
                # an exception here means we tried to timeout an admin/owner/etc
                self.bot.logger.info(f"WOTD failed to timeout user: {message.author} {e}")


    async def cog_unload(self):
        self.bot.logger.info("Cancelling wotd expire timer")
        self.expire_timer.cancel()

async def setup(bot):
    await bot.add_cog(Wotd(bot))



