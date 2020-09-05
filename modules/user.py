import discord
from discord.ext import commands
import datetime
import dateutil.parser
from dateutil import relativedelta
from utils.time import HumanTime
import pytz
from urllib.parse import quote as uriquote


class User(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="set", case_insensitive=True)
    async def _set (self, ctx):
        """Set some useful user-related variables to the bot for conveneint command usage"""
        pass

    @_set.command(name='location')
    async def _set_location(self, ctx, *, location: str):
        """Set your approximate location for things like weather and localized results. Also sets timezone automatically"""
        loc = await self.bot.utils.Location.from_google_geocode(self.bot, location)
        ctx.author_info.location = loc
        ctx.author_info.timezone = await loc.get_timezone(self.bot)
        await ctx.send(f"{ctx.author.mention} location set to: {loc.formatted_address} and timezone set to {ctx.author_info.timezone}")

    
    @_set.command(name='last.fm')
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
        await self.show_age(ctx)
        

    @commands.command()
    async def age(self, ctx, *, day: HumanTime = None):
        """Show your age if stored, or optionally return the time from [day] to now"""
        await self.show_age(ctx, day=day)

    async def show_age(self, ctx, *, day: HumanTime = None):
        if not ctx.author_info.birthday and not day:
            await ctx.send("Need to enter a birthday such as 1985-11-24")
            return
        if not ctx.author_info.timezone:
            utz = pytz.utc
        else:
            utz = pytz.timezone(ctx.author_info.timezone)
        now = datetime.datetime.now(utz)
        fromday = day if day else HumanTime(ctx.author_info.birthday, now=now, now_tz=utz)
 
        d = relativedelta.relativedelta(now, fromday.dt)
        if d.months == 0 and d.days == 0:
            out = f"{ctx.author.mention} is {d.years} years old! Happy Birthday! http://youtu.be/5qm8PH4xAss"
        elif not day:
            out = f"{ctx.author.mention} is {d.years} years, {d.months} months, and {d.days} days old"
        else:
            out = f"{str(day.dt)[:10]} is {d.years} years, {d.months} months, and {d.days} days ago"

        await ctx.send(out)

    @age.error
    @_set_birthday.error
    async def _set_birthday_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("Failed to parse date - try a different day format such as YYYY-MM-DD")
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(error)


    @commands.command()
    async def beats(self, ctx):
        now = datetime.datetime.utcnow()
        beats = (((now.minute+1) * 60) + ((now.hour+1) * 3600)) / 86.4
        await ctx.send(f'@{beats:.2f}')


        # ((UTC+1minutes * 60) + (UTC+1hours * 3600)) / 86.4

    @commands.command()
    async def time(self, ctx):
        """What time is it? Game time."""
        if ctx.author_info.timezone:
            now = datetime.datetime.utcnow()\
                                   .replace(tzinfo=pytz.utc)\
                                   .astimezone(tz=pytz.timezone(ctx.author_info.timezone))
        else:
            now = datetime.datetime.now()

        fmt = "Current time: %-I:%M:%S %p %Z | %A, %B %-d, %Y"
        time = now.strftime(fmt) + "\nhttps://i.imgur.com/HHCethk.gif"
        await ctx.send(time)
        

    @commands.command(name='np')
    async def lastfm(self, ctx, user = None):
        """Show the users last played song from last.fm"""
        user = user or ctx.author_info.lastfm
        if not user:
            await ctx.send("No user found - usage is `np <user>` or set one with `set last.fm <user>`")
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
        params = {'part' : 'snippet', 'q': uriquote(f"{artist} - {trackname}"), 'type': 'video',
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
            




        


def setup(bot):
    bot.add_cog(User(bot))
