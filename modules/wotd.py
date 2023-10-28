import discord
from discord.ext import commands
import asyncio
import random
from utils.time import human_timedelta
import sqlite3
import subprocess
from datetime import datetime,timedelta
import re


common_words = ["the", "people", "would", "really", "think", "right", "there", "about", "were", "when", "your", "can",
                "which", "each", "other", "them", "then", "into", "him", "write", "more", "their", "make", "word", "some",
                "many", "time", "look", "see", "who", "may", "down", "get", "day", "come", "part", "like", "now", "these",
                "other", "said", "could", "she"]

# Timestamp (when it was hit) | User | word | wordcount (when set) | setter | age of word in seconds (technically not required since it can be calculated but slightly easier when generating stats)
# could then check user rows for count, and user AND setter same for selfpwns.
# this could potentially lead to interesting stats
# best finder:
# select finder, count(finder) from hitlog group by finder order by count(finder);
# Longest lasting word setter:
# select setter, avg(wordage) from hitlog group by setter order by avg(wordage);
# longest lasting word in general:
# select * from hitlog order by wordage ASC;
# most commonly used wotd:
# select count(*), word from hitlog group by word order by count(*) asc;
#TODO - change hint system to be based on length of word
# probably with some 6hr grace period of no hints, then interval based on length


class WotdPrompt(discord.ui.Modal):
    def __init__(self, wotd):
        super().__init__(title="Set a new WOTD")
        self.wotd = wotd
    good_word = False
    word = ""
    fullword = False
    s_re = re.compile("[^a-z0-9!'_-]*",re.I)
    new_wotd = discord.ui.TextInput(label="New Word of the Day", min_length=3, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        word = str(self.new_wotd)
        # This might fail from those stupid fancy quotes
        # self.fullword = (word[0] == '"' and word[-1] == '"')
        self.fullword = True
        word = self.s_re.sub("", word)
        word = word.strip()
        self.word = word
        fw = ""
        if self.fullword:
            count = self.wotd.count_wotd(word, fullword=True)
            fw = "\nThis is a full-word only match. It will only hit on the complete word and not a substring of another word - the count will also reflect that"
        else:
            count = self.wotd.count_wotd(word)
        if len(word) < 3:
            self.wotd.bot.logger.info(f"Short WOTD: {word}. OG: {self.new_wotd} Fullword: {self.fullword}")
            await interaction.response.send_message(f"**{word}** only has {len(word)} characters after removing disallowed characters. It's too short to set. You can click the button to set a different one.", ephemeral=True)
            self.wotd.wotd_count = None
        elif count < 1:
            self.wotd.wotd_count = None
            self.wotd.bot.logger.info(f"Bad WOTD: {word} count: {count} Fullword: {self.fullword}")
            print(f"Bad WOTD is: {word} with {count}")
            match count:
                case 0:
                    usage = "Has **never** been used,"
                case 1:
                    usage = "Has only ever been used **once**,"
                case _:
                    usage = f"Has only ever been used **{count}** times,"
            await interaction.response.send_message(f"**{word}** {usage} and is such a terrible word that I'm not going to set it to that.\nClick the button again to set a different word that has been used at least 100 times.{fw}", ephemeral=True)
            
        else:
            self.good_word = True
            await interaction.response.send_message(f'WOTD has been set to: **{word}** which has been used **{count}** times.\nIf you want to set a new word before someone finds it use the command `!newwotd` to spawn a new button.\nYou can also use `!wotdhint` if you want the bot to give a hint.{fw}', ephemeral=True)

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
            await self.do_wotd_prompt(interaction)

    async def do_wotd_prompt(self, interaction):
        modal = WotdPrompt(self.wotd)
        await interaction.response.send_modal(modal)
        await modal.wait()
        word = str(modal.word)
        if modal.good_word:
            self.wotd.hint = ""
            self.wotd.full_word_match = modal.fullword
            self.wotd.fwr = re.compile(f"\\b{word}\\b", flags=re.IGNORECASE)
            self.wotd.bot.logger.info(f"New WOTD is: {word} - Fullword is: {modal.fullword}")
            self.wotd.wotd = word
            self.wotd.timestamp = datetime.utcnow()
            count = self.wotd.count_wotd()
            chan = self.message.channel.id
            self.wotd.single_setter(chan, "setter", self.wotd_finder.id)
            self.wotd.single_setter(chan, "timestamp", str(self.wotd.timestamp))
            self.wotd.single_setter(chan, "wotd", self.wotd.wotd)
            self.wotd.single_setter(chan, "message", self.message.id)
            self.wotd.single_setter(chan, "hint", self.wotd.hint)
            self.wotd.single_setter(chan, "fullword", modal.fullword)
            self.stop()
            msg = self.message.content + f"\n\nWord has been set. The new WOTD has been used {count} times."
            if modal.fullword:
                msg += "\nThe setter has specified full word only matching."
            await self.message.edit(content=msg, view=None)

    async def on_timeout(self):
        self.wotd.wotd = random.choice(common_words)
#        self.wotd.setter = self.wotd.bot.user
        self.wotd.timestamp = datetime.utcnow()
        self.wotd.full_word_match = False
        await self.message.channel.send("New WOTD button has expired, so it has been set to a random common word\nThe WOTD finder can still use `!newwotd` to set it again")
        await self.message.edit(content=self.message.content, view=None)



# TODO This is currently written to assume only 1 channel does WOTD and the word is the same across all servers
# The DB is designed to support multiple channels/servers but code assumes 1 specific channel


class Wotd(commands.Cog):
    wotd = ""
    setter = None
    timestamp = None
    expire_timer = None
    hint = ""
    wotd_count = None
    full_word_match = False
    fwr = re.compile("#INVALID_WORD#")

    def __init__(self, bot):
        self.bot = bot
        self.wotd = random.choice(common_words)
        self.setter = bot.user
        self.timestamp = datetime.utcnow()
        self.hint = ""

        self.conn = sqlite3.connect("wotd.sqlite")
        self.c = self.conn.cursor()

        q = '''CREATE TABLE IF NOT EXISTS 'settings' ("channel" integer, "setting" text, "value" text);'''
        self.c.execute(q)
        q = '''CREATE TABLE IF NOT EXISTS 'hitlog' ("channel" integer, "timestamp" text, "finder" integer, "word" text, "wordcount" integer, "setter" integer, "wordage" integer, "fullword" boolean);'''
        self.c.execute(q)
        self.conn.commit()

        self.bot.loop.create_task(self.load_wotd())

    
    async def load_wotd(self):
        # have to wait until ready so that it can get_channel properly
        await self.bot.wait_until_ready()
        #TODO do this properly for mutli-channel
        if self.single_getter(self.bot.config.wotd_whitelist[0], "wotd"):
            chan = self.bot.config.wotd_whitelist[0]

            self.wotd = self.single_getter(chan, "wotd")
            self.hint = self.single_getter(chan, "hint")
            self.full_word_match = int(self.single_getter(chan, "fullword")) == 1
            if self.full_word_match:
                self.fwr = re.compile(f"\\b{self.wotd}\\b", flags=re.IGNORECASE)
            setterid = self.single_getter(chan, "setter")
            try:
                self.setter = await self.bot.fetch_user(setterid)
            except:
                self.setter = self.bot.user
            ts = self.single_getter(chan, "timestamp")
            self.timestamp = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
            tssec = int((datetime.utcnow() - self.timestamp).total_seconds())
            waittime = 6*60*60 - (tssec % (6*60*60))
            
            channel = self.bot.get_channel(chan)
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
        if self.hint:
            await ctx.send("The WOTD can't be changed after a hint has been given.")
            return

        button = WotdButton(self, ctx.message.author)
        self.wotd_count = None
        self.wotd = ""
        self.hint = ""
        self.fwr = re.compile("#INVALID_WORD#")
        mymsg = await ctx.send("The WOTD owner can set a new WOTD with the button below", view=button)
        button.message = mymsg

    @commands.command(hidden=True)
    @commands.is_owner()
    async def wotdtest(self, ctx):
        """Lets you set a new WOTD for testing.
        Sets WOTD author to the bot so that you can test trigger it"""
        button = WotdButton(self, ctx.message.author)
        mymsg = await ctx.send("Nevermind this button...", view=button)
        button.message = mymsg
        self.setter = self.bot.user
        self.timestamp = datetime.utcnow()
        self.wotd = ""
        self.hint = ""
        self.wotd_count = None

    
    async def expire_word(self, channel, waittime = 6 * 60 * 60):
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
        try:
            self.single_setter(channel.id, "hint", self.hint)
        except Exception as e:
            print(e)
            print("Failed to set hint in the wotd database")
        print("Sending wotd expire message")
        hrs = int((datetime.utcnow() - self.timestamp).total_seconds()) // 60 // 60
        count = self.count_wotd()
        fw = ""
        if self.full_word_match:
            fw = " This is a full word match only, substrings will not match."
        await channel.send(f"The WOTD was set {hrs} hours ago by {self.setter.display_name} and no one has found it yet. So here's a hint: `{hint}` has been used {count} times.{fw}")
        print("Sent expire message... setting new timer")
        self.expire_timer = asyncio.ensure_future(self.expire_word(channel, 6*60*60))

    @commands.command(hidden=True)
    async def wotdhint(self, ctx):
        """Send a WOTD hint either by the word owner or the bot owner"""
        if ctx.author.id == self.setter.id or await self.bot.is_owner(ctx.author):
            self.expire_timer.cancel()
            await self.expire_word(ctx.channel, 1)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def checkwotd(self, ctx):
        """Debug function shows you the current wotd, who set it, and when"""
        ago = human_timedelta(self.timestamp, source=datetime.utcnow(), suffix=True)

        await ctx.send(f"wotd is: ||{self.wotd}|| set by **{self.setter.display_name}** on {self.timestamp} UTC {ago} - hint: `{self.hint}` - Fullword: {self.full_word_match}")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def wotdstats(self, ctx, *, query):
        # THIS COMMAND IS NOT SAFE FOR GENERAL USE
        # do not allow any usage
        # still very work in progress to generate some basic stats
        if ";" not in query:
            return
        if "limit" not in query.lower():
            return
        res = self.c.execute(query)
        names = next(zip(*res.description))
        rows = []
        rows.append(" | ".join(names))
        rows.append("--------------------")
        for row in res:
            r = []
            for col in range(len(row)):
                if names[col] == 'finder' or names[col] == 'setter':
                    user = await self.bot.fetch_user(row[col])
                    r.append(user.display_name)
                else:
                    r.append(str(row[col]))
            rows.append(" | ".join(r))

        await ctx.send("```{}```".format("\n".join(rows)))



    @commands.command(aliases=['gotd'])
    async def wotd(self, ctx):
        """Shows some stats about the current wotd"""
        if not self.wotd:
            return
        ago = human_timedelta(self.timestamp, source=datetime.utcnow(), suffix=True)

        wordcount = self.count_wotd()

        if self.hint:
            hint = f'`{self.hint}` '
        else:
            hint = ""

        fw = ""
        if self.full_word_match:
            fw = " This is a full word only match, substrings will not match."

        await ctx.send(f"The WOTD {hint}was set by **{self.setter.display_name}** {ago}.\nThe word has been used {wordcount} times in this channel.{fw}")

    s_re = re.compile("[^a-z0-9!'_-]*",re.I)

    def count_wotd(self, word = None, *, fullword=False):
        if self.wotd_count and not word:
            return self.wotd_count
        if not word and self.wotd:
            word = self.wotd

        if fullword or self.full_word_match:
            wordcount = self.count_word(word, fullword=True)
        else:
            wordcount = self.count_word(word) 
        self.wotd_count = wordcount
        return wordcount

        
    @commands.command(hidden=True, aliases=['fullwordcount'])
    async def wordcount(self, ctx, *, word):
        word = self.s_re.sub("", word)
        if len(word) < 3:
            await ctx.send(f"Word `{word}` is too short")
            return
        if ctx.invoked_with.lower() == 'fullwordcount':
            wordcount = self.count_word(word, fullword=True)
        else:
            wordcount = self.count_word(word)
        await ctx.send(f"count of {word} is {wordcount}")

    def count_word(self, word, fullword=False):
        word = self.s_re.sub("", word)
        if not word:
            return 0
        filename = f'logfiles/{self.bot.config.wotd_whitelist[0]}.log'
        if fullword:
            cmd = f'grep -ic "PRIVMSG #.* :.*\\b{word}\\b" {filename}'
        else:
            cmd = f'grep -ic "PRIVMSG #.* :.*{word}.*" {filename}'
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        wordcount = int(process.communicate(timeout=5)[0][:-1])
        return wordcount


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id not in self.bot.config.wotd_whitelist or \
           message.author.id == self.bot.user.id or \
           " " not in message.clean_content or \
           not self.wotd:
             return

        if (not self.full_word_match and self.wotd.lower() in message.clean_content.lower()) or \
                (self.full_word_match and self.fwr.search(message.clean_content.lower())):
            self.expire_timer.cancel()
            self.record_hit(message)

            count = self.hitcount(message.author.id)
            ttime = 1
            ago = human_timedelta(self.timestamp, source=datetime.utcnow(), suffix=True)
            button = WotdButton(self, message.author)
            msg = f"Congratulations? You've found the word of the day for the {self.bot.utils.ordinal(count)} time: **{self.wotd}** that was set by {self.setter.mention} {ago}. Now you can take some time and think about that.\nPlease push the button below to set a new word (after the timeout)."
            if message.author.id == self.setter.id:
                selfpwn = self.selfpwncount(message.author.id)
                ttime = 2
                msg = f"Wow. You hit your own word for the {self.bot.utils.ordinal(selfpwn)} time: **{self.wotd}** that *you* set {ago}. Now you gotta wait twice as long. You can still set a new word though after the timeout."
            banword = self.wotd
            self.wotd = ""
            self.hint = ""
            self.fwr = re.compile("#INVALID_WORD#")
            self.wotd_count = None
            self.full_word_match = False
            self.setter = message.author
            self.timestamp = datetime.utcnow()
            
            mymsg = await message.reply(msg, view=button)
            button.message = mymsg
            self.expire_timer = asyncio.ensure_future(self.expire_word(message.channel))
            try:
                await message.author.timeout(timedelta(minutes=ttime), reason=f"wotd: {banword}")
            except Exception as e:
                # an exception here means we tried to timeout an admin/owner/etc
                self.bot.logger.info(f"WOTD failed to timeout user: {message.author} {e}")

    def hitcount(self, userid):
        q = 'SELECT COUNT(*) FROM hitlog WHERE finder = (?)'
        count = int(self.c.execute(q, ([userid])).fetchone()[0])
        
        return count

    def selfpwncount(self, userid):
        q = 'SELECT COUNT(*) FROM hitlog WHERE finder = (?) AND setter = (?)'
        count = int(self.c.execute(q, (userid, userid)).fetchone()[0])
        return count

    def record_hit(self, message):
        q = "INSERT INTO hitlog VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        timestamp = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
        age = int((datetime.utcnow() - self.timestamp).total_seconds())
        self.c.execute(q, (message.channel.id, timestamp, message.author.id, self.wotd, self.count_wotd(), self.setter.id, age, self.full_word_match))
        self.conn.commit()


    async def cog_unload(self):
        self.bot.logger.info("Cancelling wotd expire timer")
        self.expire_timer.cancel()

async def setup(bot):
    await bot.add_cog(Wotd(bot))



