import discord
from discord.ext import commands
import asyncio
import random
from utils.time import human_timedelta
import aiosqlite
import subprocess
from datetime import datetime,timedelta, timezone
import re


common_words = ["the", "people", "would", "really", "think", "right", "there", "about", "were", "when", "your", "can",
                "which", "each", "other", "them", "then", "into", "him", "write", "more", "their", "make", "word", "some",
                "many", "time", "look", "see", "who", "may", "down", "get", "day", "come", "part", "like", "now", "these",
                "other", "said", "could", "she", "should"]

WCLIMIT = 1

# Timestamp (when it was hit) | User | word | wordcount (when set) | setter | age of word in seconds 
# (technically age not required since it can be calculated but slightly easier when generating stats)
# this could potentially lead to interesting stats
# best finder:
# select finder, count(finder) from hitlog group by finder order by count(finder) DESC;
# Longest lasting word setter:
# select setter, avg(wordage) from hitlog group by setter order by avg(wordage) DESC;
# longest lasting word in general:
# select * from hitlog order by wordage DESC LIMIT 5;
# most commonly used wotd:
# select count(*), word from hitlog group by word order by count(*) DESC;


# TODO This is currently written to assume only 1 channel does WOTD and the word is the same across all servers
# The DB is designed to support multiple channels/servers but code assumes 1 specific channel

# Doing a LIKE first is more efficient as it "fast-fails"
#  and filters how many results need to be regexed
F_WOTD_COUNT = """SELECT count()
FROM messages
JOIN users ON messages.user_id = users.user_id
WHERE channel_id = (?)
  AND is_bot = 0
  AND deleted = 0
  AND message LIKE (?) COLLATE NOCASE
  AND message REGEXP (?) COLLATE NOCASE
;"""

WOTD_COUNT = """SELECT count()
FROM messages
JOIN users ON messages.user_id = users.user_id
WHERE channel_id = (?)
  AND is_bot = 0
  AND deleted = 0
  AND message LIKE (?) COLLATE NOCASE
;"""

def regexp(expr, item):
    reg = re.compile(expr)
    return reg.search(item) is not None


class WotdPrompt(discord.ui.Modal):
    def __init__(self, wotd):
        super().__init__(title="Set a new WOTD")
        self.wotd = wotd
    good_word = False
    word = ""
    fullword = False
    s_re = re.compile("[^a-z0-9!'_-]*",re.I)
    new_wotd = discord.ui.TextInput(
        label="New Word of the Day", min_length=3, max_length=20, required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        word = str(self.new_wotd)
        # This might fail from those stupid fancy quotes
        self.fullword = not (word[0] == '*' and word[-1] == '*')
        # self.fullword = True
        word = self.s_re.sub("", word)
        word = word.strip()
        self.word = word
        fw = ""

        if len(word) < 3:
            self.wotd.bot.logger.info(
                f"Short WOTD: {word}. OG: {self.new_wotd} Fullword: {self.fullword}")
            out = (f"**{word}** only has {len(word)} characters after removing "
                   "disallowed characters. It's too short to set. "
                   "You can click the button again to set a different one.")
            await interaction.response.send_message(out, ephemeral=True)
            self.wotd.wotd_count = None
            return
        
        await interaction.response.defer(ephemeral=True)
        if self.fullword:
            count = await self.wotd.count_wotd(word, fullword=True)
            fw = ("\nThis is a full-word only match. "
                "It will only hit on the complete word and not a substring of another word - "
                "the count will also reflect that")
        else:
            count = await self.wotd.count_wotd(word)
        if count < WCLIMIT:
            self.wotd.wotd_count = None
            self.wotd.bot.logger.info(
                f"Bad WOTD: {word} count: {count} Fullword: {self.fullword}")
            print(f"Bad WOTD is: {word} with {count}")
            match count:
                case 0:
                    usage = "Has **never** been used,"
                case 1:
                    usage = "Has only ever been used **once**,"
                case _:
                    usage = f"Has only ever been used **{count}** times,"
            out = (f"**{word}** {usage} and is such a terrible word that "
                   "I'm not going to set it to that.\n"
                   "Click the button again to set a different word that "
                   f"has been used at least {WCLIMIT} times.{fw}")
            await interaction.followup.send(out, ephemeral=True)
            
        else:
            self.good_word = True
            out = (f'WOTD has been set to: **{word}** which has been used **{count}** times.\n'
                   'If you want to set a new word before someone finds it use the command '
                   '`!newwotd` to spawn a new button.\n'
                   f'You can also use `!wotdhint` if you want the bot to give a hint.{fw}')
            await interaction.followup.send(out, ephemeral=True)

class WotdButton(discord.ui.View):
    message = None
    def __init__(self, wotd, finder) -> None:
        super().__init__(timeout=300)
        self.wotd_finder = finder
        self.new_wotd = ""
        self.wotd:Wotd = wotd
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
            self.wotd.unrevealed = set(range(len(word)))
            self.wotd.revealed = set()
            self.wotd.full_word_match = modal.fullword
            self.wotd.fwr = re.compile(f"\\b{word}\\b", flags=re.IGNORECASE)
            self.wotd.bot.logger.info(f"New WOTD is: {word} - Fullword is: {modal.fullword}")
            self.wotd.wotd = word
            self.wotd.timestamp = datetime.now(timezone.utc)
            hinttime = 24*60*60 // len(self.wotd.wotd)
            self.wotd.expire_timer = asyncio.ensure_future(
                self.wotd.expire_word(interaction.channel, hinttime))
            count = await self.wotd.count_wotd()
            chan = self.message.channel.id
            await self.wotd.single_setter(chan, "setter", self.wotd_finder.id)
            await self.wotd.single_setter(chan, "timestamp", str(self.wotd.timestamp))
            await self.wotd.single_setter(chan, "wotd", self.wotd.wotd)
            await self.wotd.single_setter(chan, "message", self.message.id)
            await self.wotd.single_setter(chan, "hint", self.wotd.hint)
            await self.wotd.single_setter(chan, 
                                    "unrevealed", 
                                    ",".join(map(str, list(self.wotd.unrevealed))))
            await self.wotd.single_setter(chan, 
                                    "revealed", 
                                    ",".join(map(str, list(self.wotd.revealed))))
            await self.wotd.single_setter(chan, "fullword", modal.fullword)
            self.stop()
            msg = self.message.content + f"\n\nWord has been set. The new WOTD has been used {count} times."
            if modal.fullword:
                msg += "\nThis is full word only matching."
            await self.message.edit(content=msg, view=None)

    async def on_timeout(self):
        self.wotd.wotd = random.choice(common_words)
        self.wotd.unrevealed = set(range(len(self.wotd.wotd)))
        self.wotd.revealed = set()    
#        self.wotd.setter = self.wotd.bot.user
        self.wotd.timestamp = datetime.now(timezone.utc)
        self.wotd.full_word_match = False
        out = ("New WOTD button has expired, so it has been set to a random common word\n"
                "The WOTD finder can still use `!newwotd` to set it again")
        await self.message.channel.send(out)
        await self.message.edit(content=self.message.content, view=None)



class Wotd(commands.Cog):
    wotd = ""
    setter = None
    timestamp = None
    expire_timer = None
    hint = ""
    revealed = set()
    unrevealed = set()
    wotd_count = None
    full_word_match = False
    fwr = re.compile("#INVALID_WORD#")

    def __init__(self, bot):
        self.bot = bot
        self.wotd = random.choice(common_words)
        self.setter = bot.user
        self.timestamp = datetime.now(timezone.utc)
        self.hint = ""

    async def cog_load(self):
        self.conn = await aiosqlite.connect("wotd.sqlite")

        q = '''CREATE TABLE IF NOT EXISTS 'settings' (
                "channel" integer, "setting" text, "value" text,
                PRIMARY KEY (channel, setting)
            );'''
        await self.conn.execute(q)
        q = '''CREATE TABLE IF NOT EXISTS 'hitlog' (
                "channel" integer, "timestamp" text, 
                "finder" integer, "word" text, 
                "wordcount" integer, "setter" integer, 
                "wordage" integer, "fullword" boolean
            );'''
        await self.conn.execute(q)
        await self.conn.commit()

        #note I can't just 'await' this because it does wait_until_ready
        # since cog_load is called in setup_hook that can cause a deadlock
        self.bot.loop.create_task(self.load_wotd())

    async def load_wotd(self):
        # have to wait until ready so that it can get_channel properly
        await self.bot.wait_until_ready()
        #TODO do this properly for mutli-channel
        if await self.single_getter(self.bot.config.wotd_whitelist[0], "wotd"):
            chan = self.bot.config.wotd_whitelist[0]

            self.wotd = await self.single_getter(chan, "wotd")
            hint = await self.single_getter(chan, "hint")
            self.hint = hint

            revealed = await self.single_getter(chan, "revealed")
            if revealed:
                self.revealed = set(map(int, revealed.split(",")))
            else:
                self.revealed = set()
            unrevealed = await self.single_getter(chan, "unrevealed")
            if unrevealed:
                self.unrevealed = set(map(int, unrevealed.split(",")))
            else:
                self.unrevealed = set(range(len(self.wotd)))
            
            self.full_word_match = int(await self.single_getter(chan, "fullword")) == 1
            if self.full_word_match:
                self.fwr = re.compile(f"\\b{self.wotd}\\b", flags=re.IGNORECASE)
            setterid = await self.single_getter(chan, "setter")
            try:
                self.setter = await self.bot.fetch_user(setterid)
            except:
                self.setter = self.bot.user
            ts = await self.single_getter(chan, "timestamp")
            self.timestamp = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f%z")
            waittime = self.wait_time()
            
            channel = self.bot.get_channel(chan)
            self.expire_timer = asyncio.ensure_future(self.expire_word(channel, waittime))


    async def single_getter(self, channel, key):
        q = '''SELECT value FROM settings WHERE channel = (?) AND setting = (?); '''
        async with self.conn.execute(q, (channel, key)) as c:
            result = await c.fetchone()
            return result[0] if result else None

    async def single_setter(self, channel, key, value):
        q = '''INSERT OR REPLACE INTO settings VALUES (?, ?, ?); '''
        await self.conn.execute(q, (channel, key, value))
        await self.conn.commit()


    @commands.command(hidden=True)
    async def newwotd(self, ctx):
        """Lets the WOTD owner set a new word"""
        #print(f"{ctx.author} used newwotd in {ctx.channel}")
        if ctx.channel.id not in self.bot.config.wotd_whitelist or \
          ctx.author.id != self.setter.id:
            return
        if self.hint:
            await ctx.send("The WOTD can't be changed after a hint has been given.")
            return

        button = WotdButton(self, ctx.message.author)
        if self.expire_timer:
            self.expire_timer.cancel()
        self.wotd_count = None
        self.wotd = ""
        self.hint = ""
        self.revealed = set()
        self.unrevealed = set()
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
        self.timestamp = datetime.now(timezone.utc)
        self.wotd = ""
        self.hint = ""
        self.unrevealed = set()
        self.revealed = set()
        self.wotd_count = None

    
    async def expire_word(self, channel, waittime = 6 * 60 * 60):
        self.bot.logger.info(f"waiting {waittime} to expire the word")
        await asyncio.sleep(waittime)
        self.bot.logger.info("Should expire message the word now!")
        hint = ""
        if not self.hint:
            self.hint = "*" * len(self.wotd)
        if self.unrevealed:
            # new hint system reveals exactly 1 unrevealed letter each time
            # over 24 hours all letters revealed with more hints for longer words
            chosen_index = random.choice(list(self.unrevealed))
            self.revealed.add(chosen_index)
            self.unrevealed = set(range(len(self.wotd))) - self.revealed
            for i, letter in enumerate(self.wotd):
                if i in self.revealed:
                    hint += letter
                else:
                    hint += "*"
            self.hint = hint
        try:
            await self.single_setter(channel.id, "hint", self.hint)
            await self.single_setter(channel.id, 
                                "unrevealed", 
                                ",".join(map(str, list(self.unrevealed))))
            await self.single_setter(channel.id, 
                                "revealed", 
                                ",".join(map(str, list(self.revealed))))
        except Exception as e:
            print(e)
            print("Failed to set hint in the wotd database")
        # hrs = int((datetime.now(timezone.utc) - self.timestamp).total_seconds()) // 60 // 60
        ago = f"<t:{int(self.timestamp.timestamp())}:R>"
        count = await self.count_wotd()
        fw = " You must use the word in a sentence."
        if self.full_word_match:
            fw += " This is a full word match only, substrings will not match."
        out = (f"The WOTD was set {ago} by **{self.setter.display_name}** "
            f"and no one has found it yet. So here's a hint: `{self.hint}` "
            f"has been used {count} times.{fw}")
        await channel.send(out)
        
        # Might change this to self.wait_time() so that !wotdhint doesn't change the timer interval
        hinttime = 24*60*60 // len(self.wotd)
        self.expire_timer = asyncio.ensure_future(self.expire_word(channel, hinttime))


    @commands.command(hidden=True)
    async def wotdhint(self, ctx):
        """Send a WOTD hint either by the word owner or the bot owner"""
        if ctx.author.id == self.setter.id or await self.bot.is_owner(ctx.author):
            self.expire_timer.cancel()
            await self.expire_word(ctx.channel, 1)
        else:
            waittime = self.wait_time()
            nexthint = f"<t:{int(datetime.now(timezone.utc).timestamp() + waittime)}:R>"
            await ctx.send(f"You didn't set the wotd. Current hint is `{self.hint}` \
                           - The next hint will be {nexthint}")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def checkwotd(self, ctx):
        """Debug function shows you the current wotd, who set it, and when"""
        # ago = human_timedelta(self.timestamp, source=datetime.now(timezone.utc), suffix=True)
        ago = f"<t:{int(self.timestamp.timestamp())}:R>"
        hinttime = 24*60*60 // len(self.wotd)
        waittime = self.wait_time()
        nexthint = f"<t:{int(datetime.now(timezone.utc).timestamp() + waittime)}:R>"

        await ctx.send(f"""wotd is: ||{self.wotd}||
            set by **{self.setter.display_name}** on {self.timestamp} UTC {ago} 
            hint: `{self.hint}` - revealed: {self.revealed} - unrevealed: {self.unrevealed}
            Next hint: {nexthint} - every {hinttime//60} minutes
            wotd_count: {self.wotd_count}
            Fullword: {self.full_word_match}""")

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
        res = await self.conn.execute(query)
        names = next(zip(*res.description))
        rows = []
        rows.append(" | ".join(names))
        rows.append("--------------------")
        async for row in res:
            r = []
            for col in range(len(row)):
                if names[col] == 'finder' or names[col] == 'setter':
                    user = await self.bot.fetch_user(row[col])
                    r.append(user.display_name)
                else:
                    r.append(str(row[col]))
            rows.append(" | ".join(r))

        await ctx.send("```{}```".format("\n".join(rows)))



    @commands.command(name="wotd", aliases=['gotd'])
    async def _wotd(self, ctx):
        """Shows some stats about the current wotd"""
        if not self.wotd:
            return
        # ago = human_timedelta(self.timestamp, source=datetime.now(timezone.utc), suffix=True)
        ago = f"<t:{int(self.timestamp.timestamp())}:R>"

        wordcount = await self.count_wotd()

        if self.hint:
            hint = f'`{self.hint}` '
        else:
            hint = ""

        fw = ""
        if self.full_word_match:
            fw = " This is a full word only match, substrings will not match."

        out = (f"The WOTD {hint}was set by **{self.setter.display_name}** {ago}.\n"
                f"The word has been used {wordcount} times in this channel.{fw}\n"
                "You must use the word in a sentence.")
        await ctx.send(out)

    s_re = re.compile("[^a-z0-9!'_-]*",re.I)

    async def count_wotd(self, word = None, *, fullword=False):
        if self.wotd_count and not word:
            return self.wotd_count
        if not word and self.wotd:
            word = self.wotd

        if fullword or self.full_word_match:
            wordcount = await self.count_word_db(word, fullword=True)
        else:
            wordcount = await self.count_word_db(word) 
        self.wotd_count = wordcount
        return wordcount

        
    @commands.command(hidden=True, aliases=['fullwordcount'])
    async def wordcount(self, ctx, *, word):
        word = self.s_re.sub("", word)
        if len(word) < 3:
            await ctx.send(f"Word `{word}` is too short")
            return
        if ctx.invoked_with.lower() == 'fullwordcount':
            wordcount = await self.count_word_db(word, fullword=True)
        else:
            wordcount = await self.count_word_db(word)
        await ctx.send(f"count of {word} is {wordcount}")

    async def count_word_db(self, word, fullword=False):
        # Deal with the module not existing.
        if "Logger" not in self.bot.cogs:
            return WCLIMIT + 1
        
        word = word.lower()
        channel = self.bot.get_channel(self.bot.config.wotd_whitelist[0])
        db = await self.bot.cogs['Logger'].get_db(channel.guild)
        l_word = f"%{word}%"
        r_word = rf"\b{word}\b"
        if fullword:
            q = F_WOTD_COUNT
            args = [channel.id, l_word, r_word]
        else:
            q = WOTD_COUNT
            args = [channel.id, l_word]
        async with db.execute(q, args) as c:
            count = await c.fetchone()
        return int(count[0])


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
            await self.record_hit(message)

            count = await self.hitcount(message.author.id)
            ttime = 1
            ago = human_timedelta(self.timestamp, source=datetime.now(timezone.utc), suffix=True)
            button = WotdButton(self, message.author)
            msg = (f"Congratulations? You've found the word of the day for the "
                f"{self.bot.utils.ordinal(count)} time: **{self.wotd}** that was set by "
                f"{self.setter.mention} {ago}. Now you can take some time and think about that.\n"
                "Please push the button below to set a new word (after the timeout).")
            if message.author.id == self.setter.id:
                selfpwn = await self.selfpwncount(message.author.id)
                ttime = 2
                msg = (f"Wow. You hit your own word for the {self.bot.utils.ordinal(selfpwn)} time: "
                    f"**{self.wotd}** that *you* set {ago}. Now you gotta wait twice as long. "
                    "You can still set a new word though after the timeout.")
            banword = self.wotd
            self.wotd = ""
            self.hint = ""
            self.fwr = re.compile("#INVALID_WORD#")
            self.wotd_count = None
            self.full_word_match = False
            self.setter = message.author
            self.timestamp = datetime.now(timezone.utc)
            
            mymsg = await message.reply(msg, view=button)
            button.message = mymsg
            
            try:
                await message.author.timeout(timedelta(minutes=ttime), reason=f"wotd: {banword}")
            except Exception as e:
                # an exception here means we tried to timeout an admin/owner/etc
                self.bot.logger.info(f"WOTD failed to timeout user: {message.author} {e}")

    def wait_time(self):
        tssec = int((datetime.now(timezone.utc) - self.timestamp).total_seconds())
        hinttime = 24*60*60 // len(self.wotd)
        return hinttime - (tssec % hinttime)

    async def hitcount(self, userid):
        q = 'SELECT COUNT(*) FROM hitlog WHERE finder = (?)'
        async with self.conn.execute(q, ([userid])) as c:
            res = await c.fetchone()
            return int(res[0])

    async def selfpwncount(self, userid):
        q = 'SELECT COUNT(*) FROM hitlog WHERE finder = (?) AND setter = (?)'
        async with self.conn.execute(q, [userid, userid]) as c:
            res = await c.fetchone()
            return int(res[0])

    async def record_hit(self, message):
        q = "INSERT INTO hitlog VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')
        age = int((datetime.now(timezone.utc) - self.timestamp).total_seconds())
        count = await self.count_wotd()
        await self.conn.execute(q, (message.channel.id, 
                                    timestamp, message.author.id, 
                                    self.wotd, count, 
                                    self.setter.id, 
                                    age, 
                                    self.full_word_match
                                    ))
        await self.conn.commit()


    async def cog_unload(self):
        await self.conn.close()
        self.bot.logger.info("Cancelling wotd expire timer")
        self.expire_timer.cancel()

async def setup(bot):
    await bot.add_cog(Wotd(bot))



