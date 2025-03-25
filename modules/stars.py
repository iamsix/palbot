import discord
from discord.ext import commands
import aiosqlite
from yarl import URL

REJECT_LIST = ['\N{BLACK UNIVERSAL RECYCLING SYMBOL}\N{VARIATION SELECTOR-16}',
               '\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}',
               '\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}',
               '\N{BLACK LEFT-POINTING TRIANGLE}',
               '\N{BLACK RIGHT-POINTING TRIANGLE}',
               '\N{WHITE HEAVY CHECK MARK}',
               '\N{CROSS MARK}',
               '1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣',

              ]

class Stars(commands.Cog):
    # TODO: I think I need a pair of reaction-botmessage in a sqlite db?
    # in theory I could do without that but it would mean searching the starboard for the right message
    # not sure if I want to make things configurable for minimal stars etc
    # could also treat this as a pin board, but I still need to keep track of starred either way
    # so hat I don't restar
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.conn = await aiosqlite.connect("stars.sqlite3")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS 'posts' (
            'original' INTEGER UNIQUE ON CONFLICT REPLACE, 'starpost' INTEGER );""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS 'settings' (
            'guild' INTEGER, 'setting' TEXT, 'value' TEXT, 
            PRIMARY KEY (guild, setting) );""")
        await self.conn.commit()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if str(reaction.emoji) != '\N{WHITE MEDIUM STAR}':
#        if str(reaction.emoji) in REJECT_LIST:
            return
        stars = reaction.count
        message = reaction.message
        starlimit = await self.get_setting(message.guild.id, 'starlimit')
        starboard = await self.get_setting(message.guild.id, 'starboard')
        if message.channel.id == starboard:
            return
        if not starboard or not starlimit or stars < int(starlimit):
            return
        channel = self.bot.get_channel(int(starboard))
#        ctx = await self.bot.get_context(reaction.message, cls=self.bot.utils.MoreContext)

        q = '''SELECT starpost FROM posts WHERE original = (?)'''
        async with self.conn.execute(q, [(message.id)]) as c:
            result = await c.fetchone()
        if result:
            original = result[0]
        else:
            original = None

        content = f'{reaction.emoji} **{stars}** {message.channel.mention} ID: {message.id}'
        if stars == 0:
            await channel.send(f"no more stars on {reaction.message.id}")
        else:
            embed = await self.star_message(message)
        
        if not original:
            post = await channel.send(content=content, embed=embed)
            q = '''INSERT INTO posts VALUES (?, ?); '''
            await self.conn.execute(q, (message.id, post.id))
            await self.conn.commit()
        else:
            o_msg = await channel.fetch_message(original)
            await o_msg.edit(content=content, embed=embed)

    async def star_message(self, message):
            embed = discord.Embed(description=message.content)
            if message.embeds:
                data = message.embeds[0]
                if data.type == 'image' and data.url:
                    # imgur urls are stupidly returned wrong by discord sometimes
                    if 'imgur' in data.url and not data.url.endswith(('png', 'jpeg', 'jpg', 'gif', 'webp')):
                        imgururl = URL(data.url).with_host('i.imgur.com')
                        embed.set_image(url=str(imgururl)+".jpg")
                    else:
                        embed.set_image(url=data.url)
                if data.type == 'rich' and data.image and data.image.url:
                    embed.set_image(url=data.image.url)

            if message.attachments:
                file = message.attachments[0]
                if file.filename.lower().endswith(('png', 'jpeg', 'jpg', 'gif', 'webp')):
                    embed.set_image(url=file.url)
                else:
                    embed.add_field(name='Attachment', value=f'[{file.filename}]({file.url})', inline=False)

            ref = message.reference
            if ref and isinstance(ref.resolved, discord.Message):
                embed.add_field(name='Replying to...', value=f'[{ref.resolved.author}]({ref.resolved.jump_url})', inline=False)

            embed.add_field(name='Original', value=f'[Jump!]({message.jump_url})', inline=False)
            embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
            embed.timestamp = message.created_at
            return embed

    async def setting_set(self, guild, setting, val):
        q = '''INSERT OR REPLACE INTO settings VALUES(?, ?, ?);'''
        await self.conn.execute(q, (guild, setting, val))
        await self.conn.commit()

    async def get_setting(self, guild, setting):
        q = '''SELECT value FROM settings WHERE guild = (?) AND setting = (?); '''
        async with self.conn.execute(q, (guild, setting)) as c:
            result = await c.fetchone()
            return result[0] if result else None
    
    @commands.command()
    @commands.has_any_role('Admins', 'GOD')
    async def starboard(self, ctx):
        await self.setting_set(ctx.guild.id, 'starboard', ctx.channel.id)
        await ctx.send(f"The starboard for {ctx.guild} is now set to #{ctx.channel}")

    @commands.command()
    @commands.has_any_role('Admins', 'GOD')
    async def starlimit(self, ctx, *, limit: int):
        await self.setting_set(ctx.guild.id, 'starlimit', limit)
        await ctx.send(f"The starboard on {ctx.guild} now requires **{limit}** stars")



async def setup(bot):
    await bot.add_cog(Stars(bot))
