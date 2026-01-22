import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import random
import re
import aiosqlite
from datetime import timedelta, datetime, timezone
import base64

FACES = [" ͡° ͜ʖ ͡°", " ͡° ʖ̯ ͡°", " ͠° ͟ʖ ͡°", " ͡ᵔ ͜ʖ ͡ᵔ", " . •́ _ʖ •̀ .", " ఠ ͟ʖ ఠ", " ͡ಠ ʖ̯ ͡ಠ",
         " ಠ ʖ̯ ಠ", " ಠ ͜ʖ ಠ", " ͡• ͜ʖ ͡• ", " ･ิ ͜ʖ ･ิ", " ͡ ͜ʖ ͡ ", "≖ ͜ʖ≖", "ʘ ʖ̯ ʘ", "ʘ ͟ʖ ʘ",
         "ʘ ͜ʖ ʘ", "* ^ ω ^", "´ ∀ ` *", "◕‿◕｡", "≧▽≦", "o^▽^o", "⌒▽⌒", "*⌒―⌒*",
         "・∀・", "´｡• ω •｡`", "￣ω￣", "°ε° ", "o･ω･o", "＠＾◡＾", "*・ω・", "^人^", "o´▽`o",
         "*´▽`*", " ﾟ^∀^ﾟ", " ´ ω ` ", "≧◡≦", "´• ω •`", "⌒ω⌒", "*^‿^*", "◕‿◕", "*≧ω≦*",
         "｡•́‿•̀｡", "ー_ー", "´ー` ", "‘～` ", "　￣д￣", "￣ヘ￣", "￣～￣　", "ˇヘˇ", "︶▽︶", 
         "ツ", " ´ д ` ", "︶︿︶", " ˘ ､ ˘ ", " ˘_˘ ", " ᐛ ", "・_・", "⇀_⇀", "￢_￢" ]
SHRUG = r"¯\\\_({})\_/¯"


class TestView(discord.ui.View):
    @discord.ui.button(label="Hello", emoji="\U0001f590", style=discord.ButtonStyle.blurple)
    async def on_click_hello(self, interaction, button):
        await interaction.response.send_message(f"Hi {interaction.user.mention}", ephemeral=True)


class CmdPrompt(discord.ui.Modal):
    def __init__(self, chat):
        self.chat = chat
        super().__init__(title="Command to send")
    command = discord.ui.TextInput(label='Command', placeholder="okaymixy")

    async def on_submit(self, interaction: discord.Interaction):
        cmd = self.command.value
        if cmd.startswith("!"):
            cmd = cmd[1:]
        response = await self.chat.custom_command(cmd)
        if response:
            allowed_mentions = discord.AllowedMentions(users=[interaction.user], 
                                                       everyone=False, 
                                                       roles=False)
            await interaction.response.send_message(response, allowed_mentions=allowed_mentions)
        else:
            await interaction.response.send_message(
                f"No command `{self.command}` found.\nNote this can only do custom commands, not 'real' ones.", 
                ephemeral=True)


class Chat(commands.Cog):    
    reminders = set()
    def __init__(self, bot):
        self.bot = bot

        self.cmd_menu = app_commands.ContextMenu(name='React Command', callback=self.command_ctx)
        self.bot.tree.add_command(self.cmd_menu)

    async def cog_load(self):
        self.tags_conn = await aiosqlite.connect("tags.sqlite")
        q = '''CREATE TABLE IF NOT EXISTS 'tags' (
            "untag_timestamp" integer, 
            "guild" integer, 
            "user" integer, 
            "tag" integer, 
            "plaintext" text);'''
        await self.tags_conn.execute(q)
        
        self.custom_command_conn = await aiosqlite.connect("customcommands.sqlite")
        await self.custom_command_conn.execute(
            "CREATE TABLE IF NOT EXISTS 'commands' ("
            "'cmd' TEXT UNIQUE ON CONFLICT REPLACE, "
            "'output' TEXT, 'owner' TEXT, 'description' TEXT);")
        

        cfind_q = """
        CREATE VIRTUAL TABLE IF NOT EXISTS cfind USING FTS5(cmd, description);
        INSERT INTO cfind(cmd, description)
            SELECT cmd, description FROM commands
            WHERE NOT EXISTS (SELECT 1 FROM cfind WHERE cfind.cmd = commands.cmd);

        CREATE TRIGGER IF NOT EXISTS cfindd AFTER DELETE ON commands BEGIN
            DELETE FROM cfind WHERE cmd = old.cmd;
        END;

        CREATE TRIGGER IF NOT EXISTS cfindi AFTER INSERT ON commands BEGIN
            INSERT INTO cfind(cmd, description) VALUES (new.cmd, new.description);
        END;

        CREATE TRIGGER IF NOT EXISTS cfindu AFTER UPDATE ON commands BEGIN
            DELETE FROM cfind WHERE cmd = old.cmd;
            INSERT INTO cfind(cmd, description) VALUES (new.cmd, new.description);
        END;"""
        await self.custom_command_conn.executescript(cfind_q)
        await self.custom_command_conn.commit()

        self.check_userthings.start()

    
    REPOST = ['\N{REGIONAL INDICATOR SYMBOL LETTER R}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER E}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER P}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER O}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER S}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER T}',]

    RIPOSTE = ['\N{REGIONAL INDICATOR SYMBOL LETTER R}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER I}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER P}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER O}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER S}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER T}',
              '\N{REGIONAL INDICATOR SYMBOL LETTER E}',]
    
    async def command_ctx(self, interaction: discord.Interaction, message: discord.Message):
        md = CmdPrompt(self)
        await interaction.response.send_modal(md)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if reaction.emoji == '\N{BLACK UNIVERSAL RECYCLING SYMBOL}\N{VARIATION SELECTOR-16}':
            for letter in self.REPOST:
                await reaction.message.add_reaction(letter)
        elif reaction.emoji == '\N{FENCER}':
            for letter in self.RIPOSTE:
                await reaction.message.add_reaction(letter)

    @commands.command()
    async def fruits(self, ctx):
        """The great fruit poll"""

        FRUITS = ['\N{GRAPES}',
            '\N{WATERMELON}',
            '\N{BANANA}',
            '\N{PINEAPPLE}',
            '\N{RED APPLE}',
            '\N{PEAR}',
            '\N{PEACH}',
            '\N{CHERRIES}',
            '\N{STRAWBERRY}',
            '\N{BLUEBERRIES}',
            '\N{KIWIFRUIT}',
            '\N{TANGERINE}',
            '\N{LEMON}',
            '\N{MELON}']
        msg = await ctx.send("The great fruit poll")
        for fruit in FRUITS:
            await msg.add_reaction(fruit)

    @commands.command(name='qp')
    async def quickpoll(self, ctx):
        """Add a Checkmark and X to your post for a quick yes-no poll"""
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')
        await ctx.message.add_reaction('\N{CROSS MARK}')

    @commands.command()
    async def mermaid(self, ctx, *, arg):
         """Output a merdmaid chart of the given input"""
         url = 'https://mermaid.ink/img/' 
         url += base64.b64encode(arg.encode('ascii')).decode('ascii')
         url += "?bgColor=000&theme=dark"
         await ctx.message.reply(url)

    @commands.command(hidden=True)
    async def testbutton(self, ctx):
        test = TestView()
        await ctx.send("What does this do...", view=test)

    @commands.command()
    async def poll(self, ctx, *, msg):
         """Create a poll using reactions.
                 !poll 1. cats 2. dogs 3. birds

                 !poll what's for lunch?
                 1) pizza
                 2) chicken
                 3) starvation
         """
         options = re.split(r"(\d\.|\d\))", msg)
         emoji = ['0️⃣', '1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣']
         for opt in options[1:]:
             try:
                 number = int(opt[0])
                 await ctx.message.add_reaction(emoji[number])
             except:
                 pass
            
    @commands.command(hidden=True, aliases=['onions'])
    async def ban(self, ctx):
        if ctx.invoked_with.lower() == "onions":
            await ctx.message.reply(f"How about these onions. <:LEOKEK:803268251064729670>")
        else:
            await ctx.message.reply(f"OK, you've been banned. <:LEOKEK:803268251064729670>")
        try:
            await ctx.message.author.timeout(timedelta(minutes=1), reason="!ban")
        except:
            self.bot.logger.info(f"Failed to timeout {ctx.author}")


    @commands.command(aliases=['tr'])
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
        params = {'client': 'gtx', 'sl': sl, 'tl': tl, 'dt': 't', "q": phrase}
        ua = "Mozilla/5.0 (X11; CrOS x86_64 12239.19.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.38 Safari/537.36"
        headers = {'User-Agent': ua}
        async with self.bot.session.get(url, headers=headers, params=params) as resp:
            result = await resp.json()
            await ctx.send("{} ({}): {}".format(result[0][0][1], result[2], result[0][0][0]))



    @commands.Cog.listener()
    async def on_message(self, message):
        self.bot.logger.debug(message)
        self.bot.logger.debug(message.content)
        out = ''
        prefix = self.bot.command_prefix
        lower = message.content.lower()
        if lower.startswith('bot '):
            decide = self.decider(message.content[4:])
            if decide:
                out = f"{message.author.mention}: {decide}"
        elif "shrug" in lower:
            out = self.shrug()
        elif message.content[:1] in prefix and message.author.id != self.bot.user.id:
            cmd = lower[1:].split(" ")[0]
            #if cmd not in self.bot.all_commands:
            out = await self.custom_command(cmd)
        if out:
            ctx = await self.bot.get_context(message, cls=self.bot.utils.MoreContext)
            allowed_mentions = discord.AllowedMentions(users=[message.author], 
                                                       everyone=False, 
                                                       roles=False)
            await ctx.send(out, allowed_mentions=allowed_mentions)

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
        
    @app_commands.command()
    async def command(self, interaction: discord.Interaction, command: str):
        """Do a custom command"""
        res = await self.custom_command(command)
        if res:
            allowed_mentions = discord.AllowedMentions(users=[interaction.user], 
                                                       everyone=False, 
                                                       roles=False)
            await interaction.response.send_message(res, allowed_mentions=allowed_mentions)
        else:
            await interaction.response.send_message(
                f"No such command `{command}`", 
                ephemeral=True,
                )

    @command.autocomplete('command')
    async def command_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        c = self.custom_command_conn
        q = "SELECT cmd, description FROM commands WHERE cmd LIKE (?);"
        async with c.execute(q, [f"%{current}%"]) as c:
            res = await c.fetchall()
        res = res[:24]
        return [
            app_commands.Choice(
                name=f"{command[0]} - {command[1][:70]}" if command[1] else command[0], 
                value=command[0]
                )
            for command in res
        ]
 
    async def custom_command(self, command):
        c = self.custom_command_conn
        try:
            async with c.execute("SELECT output FROM commands WHERE cmd = (?)", 
                            [command.lower()]) as c:
                result = await c.fetchone()
                return result[0].strip() if result else None
        except aiosqlite.ProgrammingError:
            #Means the DB is closed
            return None
    
    pdlre = re.compile(r'poorlydrawnlines.com/wp-content/uploads/\d{4}/\d{2}/')
    @commands.command()
    async def pdl(self, ctx, *, td: str = ""):
        """Show a random poorlydrawnlines comic. Add 'today' to show the latest."""
        url = "https://poorlydrawnlines.com/?random=true"
        if td.lower() == "today":
            url = "https://poorlydrawnlines.com/"
        pg = await self.bot.utils.bs_from_url(self.bot, url)
        div = pg.find('div', attrs={'class' : "entry-content"})
        comic = div.find('img',src=self.pdlre)
        await ctx.send(comic.get('src'))

    @commands.command()
    async def xkcd(self, ctx, *, td: str = ""):
        """Show a random XKCD. Add 'today' to show the latest."""
        url = "https://c.xkcd.com/random/comic/"
        try:
            url = f"https://xkcd.com/{int(td)}/"
        except:
            pass
        if td.lower() == "today":
            url = "https://xkcd.com/"
        pg = await self.bot.utils.bs_from_url(self.bot, url)
        div = pg.find('div', attrs={'id' : "comic"})
        img = div.find('img')
        out = img.get("title") + "\n"
        out += "https:" + img.get('src')
        await ctx.send(out)


    @commands.command()
    async def mock(self, ctx, *, text: str):
        """Converts text to mOcKiNg CaSe"""
        mocked = ''.join(c.upper() if random.randint(0,1) else c.lower() for c in text)
        await ctx.send(mocked)

    @commands.command()
    async def find(self, ctx, find: str):
        """Find a custom command
        
        Attributes
        -----------
        find: str
            What to search for in the cmmand name or description
        """
        conn = self.custom_command_conn
        q = "SELECT commands.cmd, output, commands.description FROM commands " \
            "JOIN cfind ON commands.cmd = cfind.cmd WHERE cfind MATCH (?) ORDER BY rank;"

        async with conn.execute(q, [find]) as c:
            lines = []
            async for row in c:
                desc = (row[2].strip() if row[2] else 'No description')
                lines.append(f"**!{row[0].strip()}** *{desc}*")
                
            if lines:
                await ctx.send("\n".join(lines))
            else:
                await ctx.send("Not found")
        
    @commands.command(hidden=True)
    async def describecommand(self, ctx, command: str, *, description: str):
        """Describes the custom command

        Attributes
        -----------
        cmd: str
            The command to add. such as `lol` - No need to add the ! 
        description: str
            The general description of what is in the command
        """
        c = self.custom_command_conn
        if command.startswith("!"):
            command = command[1:]
        async with c.execute(
            "SELECT output FROM commands WHERE cmd = (?)", [command.lower()]) as c:
            result = await c.fetchone()
        if not result:
            await ctx.send(f"No such command `{command}`")
            return
        
        c = self.custom_command_conn
        q = "UPDATE commands SET description=(?) WHERE cmd = (?)"
        result = await c.execute(q, (description, command))
        await c.commit()
        await ctx.send(f"!{command}: {description}")

    @commands.command()
#    @commands.has_role('Admins')
    async def addcmd(self, ctx, cmd, *, output: str):
        """Adds a custom command to the bot that will output whatever is in the <output> field

        Attributes
        -----------
        cmd: str
            The command to add. such as `lol` - No need to add the ! 
        output: str
            The output of the command. Can be a URL if you want it to show an image/link/etc
        """
        #Currently hard insert so can be used to edit too
        if cmd.startswith("!"):
            cmd = cmd[1:]
        if cmd in self.bot.all_commands:
            await ctx.send("No shadowing real commands.")
            return
        owner = str(ctx.author)
        conn = self.custom_command_conn
        await conn.execute("INSERT INTO commands VALUES (?,?,?,?)",
                            (cmd.lower(), output, owner, ""))
        await conn.commit()
            
    @commands.command()
    @commands.has_any_role('Admins', 'GOD')
    async def delcmd(self, ctx, cmd: str):
        conn = self.custom_command_conn
        await conn.execute("DELETE FROM commands WHERE cmd = (?)", [cmd.lower()])
        await conn.commit()


    @commands.command()
    @commands.has_any_role('Admins', 'GOD')
    async def tag(self, ctx, user: discord.Member, tag: discord.Role):
        """Tag a user"""
        # might change the interface to only work on replies
  
        await user.add_roles(tag, reason=f"{ctx.author.display_name} used !tag")
  
        when = int(datetime.now(timezone.utc).timestamp() + (7 * 24 * 60 * 60))
        plaintext = f"Untag `{tag}` from `{user.display_name}` in `{ctx.guild}` on: {datetime.fromtimestamp(when)} UTC"
        q = "INSERT INTO tags VALUES (?, ?, ?, ?, ?)"
        await self.tags_conn.execute(q, (when,ctx.guild.id, user.id, tag.id, plaintext))
        await self.tags_conn.commit()

    @tasks.loop(minutes=60)
    async def check_userthings(self):
        # TODO : Check user birthdays here and set/unset birthday tag automagically
        # I'll have to assume the guild as I don't have that recorded in the userdata db


        for reminder in self.reminders:
            reminder.cancel()
        self.reminders.clear()
        ts = int(datetime.now(timezone.utc).timestamp())
        ts += 60*60

        q = 'SELECT untag_timestamp, guild, user, tag, plaintext FROM tags WHERE untag_timestamp <= ?'
        async with self.tags_conn.execute(q, [(ts)]) as res:
            async for row in res:
                self.bot.logger.debug("tagloop:", row[4])
                when = datetime.fromtimestamp(row[0])
                when = when.replace(tzinfo=timezone.utc)
                guild = await self.bot.fetch_guild(row[1])
                user = await guild.fetch_member(row[2])
                tag = guild.get_role(row[3])

                task = asyncio.create_task(self.untag(when, user, tag))
                self.reminders.add(task)
                task.add_done_callback(self.reminders.discard)

    async def untag(self, when, user, tag):
        seconds = max(0,int((when - datetime.now(timezone.utc)).total_seconds()))
        self.bot.logger.debug(f"untag: {user} tag: {tag} waiting: {seconds}s")
        await asyncio.sleep(seconds)
        try:
            await user.remove_roles(tag, reason="expired 7 days")
        except Exception as e:
            print(e)
        

        q = 'DELETE FROM tags WHERE untag_timestamp <= ?'
        await self.tags_conn.execute(q, [(int(when.timestamp()))])
        await self.tags_conn.commit()


    async def cog_unload(self):
        await self.custom_command_conn.close()
        await self.tags_conn.close()
        self.bot.tree.remove_command(self.cmd_menu)
        self.check_userthings.cancel()
        # cancel all the timers here
        for reminder in self.reminders:
            reminder.cancel()
        self.reminders.clear()


async def setup(bot):
    await bot.add_cog(Chat(bot))
