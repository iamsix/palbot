import discord
from discord.ext import commands
import datetime
import dateutil.parser

class User(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="set")
    async def _set (self, ctx):
        """Set some useful user-related variables to the bot for conveneint command usage"""
        pass

    @_set.command(name='location')
    async def _set_location(self, ctx, *, location:str):
        """Set your approximate location for things like weather and localized results. Also sets timezone automatically"""
        loc = self.bot.utils.Location.from_google_geocode(location)
        ctx.author_info.location = loc
        ctx.author_info.timezone = loc.get_timezone()
        ctx.send(f"{ctx.author.mention} location set to: {loc.formatted_address}")

    
    @_set.command(name='last.fm')
    async def _set_lastfm(self, ctx, user:str):
        """Set your last.fm user name for !np"""
        ctx.author_info.lastfm = user
        ctx.send(f"{ctx.author.mention} last.fm user set to: {user}")

    @_set.command(name='strava')
    async def _set_strava(self, ctx, user:int):
        """Set your strava athlete ID such as https://www.strava.com/athletes/<######> """
        ctx.author_info.strava = str(user)
        ctx.send(f"{ctx.author.mention} strava ID set to: {user}")

    @_set.command(name='birthday')
    async def _set_birthday(self, ctx, *, bday:str):
        """Set your birthday for things like !age"""
        try:
            _ = dateutil.parser.parse(bday)
        except:
            ctx.send("Failed to parse birthday")
            return
        
        ctx.author_info.birthday = bday
        await self.age(ctx, bday=bday)
        

    @commands.command()
    async def age(self, ctx, *, day:str = ''):
        """Return a user's age if stored, or optionally return the time from <day> to now"""
        fromday = day if day else ctx.author_info.birthday

        try:
            daydt = dateutil.parser.parse(fromday)
        except ValueError:
            ctx.send("Failed to parse birthday - try a different date format like YYYY-MM-DD")
            return
        
        now = datetime.datetime.now()
        d = relativedelta.relativedelta(now, daydt)
        if d.months == 0 and d.days == 0:
            ctx.send(f"{ctx.author.mention} is {d.years} years old! Happy Birthday! http://youtu.be/3nONOuNEhhE")
        elif not day:
            ctx.send(f"{ctx.author.mention} is {d.years} years, {d.months} months, and {d.days} days old")
        else:
            ctx.send(f"{day} is {d.years} years, {d.months} months, and {d.days} days ago")




def setup(bot):
    bot.add_cog(User(bot))