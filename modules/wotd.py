import discord
from discord.ext import commands
import asyncio
import random
from datetime import datetime, timedelta
from utils.time import human_timedelta

common_words = ["the", "people", "would", "really", "think", "right", "there", "about", "were", "when", "your", "can",
                "which", "each", "other", "them", "then", "into", "him", "write", "more", "their", "make", "word", "some",
                "many", "time", "look", "see", "who", "may", "down", "get", "day", "come", "part", "like", "now", "these",
                "other", "said", "could", "she"]


# TODO : Make the WOTD expire after 24hr? 48hr? 1wk? 
# TODO : Count the number of times each user has hit the wotd
# TODO : Save the wotd for loading/realoading etc

class WotdPrompt(discord.ui.Modal, title="Set a new WOTD"):
    new_wotd = discord.ui.TextInput(label="New Word of the Day", min_length=3, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'WOTD has been set to: **{self.new_wotd}**.\nRemember, *you* can say this word to bait people.', ephemeral=True)

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
            self.stop()
            await self.message.edit(content=self.message.content, view=None)

    async def on_timeout(self):
        self.wotd.wotd = random.choice(common_words)
        self.wotd.setter = self.wotd.bot.user
        self.wotd.timestamp = datetime.utcnow()
        await self.message.channel.send("New WOTD button has expired, so it has been set to a random common word")
        await self.message.edit(content=self.message.content, view=None)




class Wotd(commands.Cog):
    wotd = ""
    setter = None
    timestamp = None

    def __init__(self, bot):
        self.bot = bot
        self.wotd = random.choice(common_words)
        self.setter = bot.user
        self.timestamp = datetime.utcnow()


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


    @commands.command(hidden=True)
    @commands.is_owner()
    async def checkwotd(self, ctx):
        """Shows you the current wotd, who set it, and when"""
        await ctx.send(f"wotd is: ||{self.wotd}|| set by **{self.setter.display_name}** on {self.timestamp} UTC")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id not in self.bot.config.wotd_whitelist or \
           message.author.id == self.bot.user.id or \
           " " not in message.content or \
           message.author.id == self.setter.id or \
           not self.wotd:
             return

        if self.wotd.lower() in message.content.lower():
            ago = human_timedelta(self.timestamp, source=datetime.utcnow(), suffix=True)
            button = WotdButton(self, message.author)
            mymsg = await message.reply(f"Congratulations? You've found the word of the day: **{self.wotd}** that was set by {self.setter.mention} {ago}. Now you can take some time and think about that.\nPlease push the button below to set a new word (after the timeout).", view=button)
            button.message = mymsg
            self.wotd == ""
            self.setter = message.author
            self.timestamp = datetime.utcnow()
            try:
                await message.author.timeout(timedelta(minutes=1), reason=f"wotd {self.wotd}")
            except:
                # an exception here means we tried to timeout an admin/owner/etc
                self.bot.logger.info(f"WOTD failed to timeout user: {message.author}")



async def setup(bot):
    await bot.add_cog(Wotd(bot))



