import discord
from discord import app_commands
from discord.ext import commands
import datetime
import dateutil.parser
from dateutil import relativedelta
from utils.time import HumanTime
import pytz
from urllib.parse import quote as uriquote
import asyncio


class User(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.age_ctx_menu = app_commands.ContextMenu(name='Age', callback=self.age_ctx)
        self.bot.tree.add_command(self.age_ctx_menu)

    def cog_unload(self):
        self.bot.tree.remove_command(self.age_ctx_menu)

#    @commands.command()
#    async def roles (self, ctx):
#        await ctx.send(str(ctx.author.roles))

#    @commands.command()
#    async def tagme (self, ctx, *, role: discord.Role):
#        if role < discord.utils.get(ctx.guild.roles, name="Tagger"):
#            await ctx.author.add_roles(role, reason="User self-request")
#            await ctx.send(f"{ctx.author.mention} is now tagged as {role}")
#        else:
#            await ctx.send("No.")
#    @tagme.error
#    async def tagme_error(self, ctx, error):
#        await ctx.send(str(error))

    async def age_ctx(self, interaction: discord.Interaction, user: discord.User):
        userinfo = interaction.client.utils.AuthorInfo(user)
        if userinfo and userinfo.birthday:
            age = await self.show_age(userinfo)
            await interaction.response.send_message(age)
        else:
            await interaction.response.send_message(f"{user.mention} has no birthday info entered.")


    @commands.command()
    async def whopper (self, ctx):
        tag = discord.utils.get(ctx.guild.roles, name="WHOPPER WHOPPER WHOPPER WHOPPER")
        await ctx.author.add_roles(tag, reason="!whopper")
        await ctx.reply("You have been given the 12 hour whopper buff, go forth and use this power wisely!")
        await asyncio.sleep(12 * 60 * 60)
        await ctx.author.remove_roles(tag, reason="the whopper has worn off")

    @commands.command()
    async def bounce (self, ctx):
        await ctx.send(file=discord.File("../media/yeah_Bounce.webm"))

    @commands.group(name="set", case_insensitive=True)
    async def _set (self, ctx):
        """Use '!help set' for more info. Lets you set user related information for convenience"""
        pass

    @_set.command(name='location')
    async def _set_location(self, ctx, *, location: str):
        """Set your approximate location for things like weather and localized results. Also sets timezone automatically"""
        loc = await self.bot.utils.Location.from_google_geocode(self.bot, location)
        ctx.author_info.location = loc
        ctx.author_info.timezone = await loc.get_timezone(self.bot)
        await ctx.send(f"{ctx.author.mention} location set to: {loc.formatted_address} and timezone set to {ctx.author_info.timezone}")

    
    @_set.command(name='last.fm', aliases=['np', 'lastfm'])
    async def _set_lastfm(self, ctx, user: str):
        """Set your last.fm user name for !np"""
        ctx.author_info.lastfm = user
        await ctx.send(f"{ctx.author.mention} last.fm user set to: {user}")

    @_set.command(name='strava')
    async def _set_strava(self, ctx, user: int):
        """Set your strava athlete ID such as https://www.strava.com/athletes/<######> """
        ctx.author_info.strava = str(user)
        await ctx.send(f"{ctx.author.mention} strava ID set to: {user}, now go ride bikes!")
    @_set_strava.error
    async def _set_strava_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("Failed to set user ID - it should be the number on your profile page URL\n"
                           "For example: <https://www.strava.com/athletes/6188> your ID would be `6188`")
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(error)

    @_set.command(name='birthday', aliases=['age'])
    async def _set_birthday(self, ctx, *, bday: HumanTime):
        """Set your birthday for things like age"""
        
        ctx.author_info.birthday = str(bday.dt)
        age = await self.show_age(ctx.author_info)
        await ctx.send(age)
        

    @commands.command()
    async def age(self, ctx, *, day: HumanTime = None):
        """Show your age if stored, or optionally return the time from [day] to now"""
        age = await self.show_age(ctx.author_info, day=day)
        await ctx.send(age)


    async def show_age(self, author_info, *, day: HumanTime = None):
        if not author_info.birthday and not day:
            return "Need to enter a birthday such as `!age 1985-10-26` or set it with `!set age 1955-11-05`"
        if not author_info.timezone:
            utz = pytz.utc
        else:
            utz = pytz.timezone(author_info.timezone)
        now = datetime.datetime.now(utz)
        fromday = day if day else HumanTime(author_info.birthday, now=now, now_tz=utz)
        now = now + datetime.timedelta(seconds=2)

        d = relativedelta.relativedelta(now, fromday.dt)
        if d.months == 0 and d.days == 0:
            out = f"<@{author_info.id}> is {d.years} years old! Happy Birthday! http://youtu.be/5qm8PH4xAss"
        elif not day:
            out = f"<@{author_info.id}> is {d.years} years, {d.months} months, and {d.days} days old"
        else:
            out = f"{str(day.dt)[:10]} is {d.years} years, {d.months} months, and {d.days} days ago"
        
        return out

    @age.error
    @_set_birthday.error
    async def _set_birthday_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("Failed to parse date - try a different day format such as YYYY-MM-DD")
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(error)
        else:
            print(error)


    @commands.command()
    async def beats(self, ctx):
        """https://beats.wiki/"""
        now = datetime.datetime.now(datetime.timezone.utc)
        beats = (((now.minute+1) * 60) + ((now.hour+1) * 3600)) / 86.4
        await ctx.send(f'@{beats:.2f}')


        # ((UTC+1minutes * 60) + (UTC+1hours * 3600)) / 86.4

    @commands.command()
    async def time(self, ctx):
        """What time is it? Game time."""
        if ctx.author_info.timezone:
            now = datetime.datetime.now(tz=pytz.utc)\
                                   .astimezone(tz=pytz.timezone(ctx.author_info.timezone))
        else:
            now = datetime.datetime.now(pytz.utc)

        fmt = "Current time: %-I:%M:%S %p %Z | %A, %B %-d, %Y"
        
        #time = now.strftime(fmt) + "\nhttps://cdn.betterttv.net/emote/627528343c6f14b688472081/3x.gif"
        time = now.strftime(fmt) + "\nhttps://tenor.com/view/judge-judy-gif-5714654"
        await ctx.send(time)
        

    @commands.command(name='np')
    async def lastfm(self, ctx, user = None):
        """Show the users last played song from last.fm"""
        user = user or ctx.author_info.lastfm
        if not user:
            await ctx.send("No user found - usage is `np <user>` or set one with `!set last.fm <user>`")
            return

        url = "http://ws.audioscrobbler.com/2.0/"
        params = {'api_key': self.bot.config.lastfm_api_key, 'limit': 1, 
                  'format': 'json','method': 'user.getRecentTracks', 'user': uriquote(user)}

        async with self.bot.session.get(url, params=params) as resp:
            npdata = await resp.json()
            if not 'recenttracks' in npdata or not npdata['recenttracks']['track']:
                await ctx.send(f"Unable to find recent tracks for user `{user}`")
                return

        params['artist'] = artist = npdata['recenttracks']['track'][0]['artist']['#text']
        params['track'] = trackname = npdata['recenttracks']['track'][0]['name']
        params['method'] = "track.getInfo"

        async with self.bot.session.get(url, params=params) as resp:
            track = await resp.json()
            track = track.get('track', None)        
        extended = ""
        if track:
            dmin, dsec = divmod((int(track.get('duration', 0)) / 1000), 60)
            duration = " [{:.0f}:{:02.0f}]".format(dmin, dsec)
            playcount = f" :: Playcount: {track['userplaycount']}" if 'userplaycount' in track else ''
            genres = []
            for genre in track['toptags']['tag']:
                genres.append(genre['name'])
            genre = f" ({', '.join(genres)})" if genres else ''

            extended = f"{duration}{playcount}{genre}"

        ytkey = self.bot.config.gsearch2
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {'part' : 'snippet', 'q': f"{artist} - {trackname}", 'type': 'video',
                  'maxResults': 1, 'key' : ytkey}
        async with self.bot.session.get(url, params=params) as resp:
            data = await resp.json()
            if data['items']:
                yt_id = data['items'][0]['id']['videoId']
                link = f" - <https://youtu.be/{yt_id}>"
            else:
                link = ""
        
        if len(npdata['recenttracks']['track']) == 1:
            #User not currently playing track
            date = npdata['recenttracks']['track'][0]['date']['#text']
            out = f"{user} last played: {artist} - {trackname} {extended} on {date}{link}"
        else:
            out = f"{user} np: {artist} - {trackname} {extended}{link}"

        await ctx.send(out)

        # TODO : last.fm compare - was never really used much
            




        


async def setup(bot):
    await bot.add_cog(User(bot))
