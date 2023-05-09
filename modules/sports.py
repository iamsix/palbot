import discord
from discord.ext import commands
import asyncio
from utils.time import HumanTime
import pytz
import datetime


class Sports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def sports_date(self, ctx, date):
        if not date:
            if ctx.author_info.timezone:
                return datetime.datetime.now(pytz.timezone(ctx.author_info.timezone))
            else:
                return datetime.datetime.now(pytz.timezone("US/Eastern"))
        else:
            return date.dt


    MLB_TEAMS = [
         144, #   'ATL',
         114, #   'CLE',
         147, #   'NYY',
         121, #   'NYM',
         111, #   'BOS',
         110, #   'BAL',
         133, #   'OAK',
         137, #   'SF',
         119, #   'LAD'
        ]

    @commands.command()
    async def mlb(self, ctx, *, date: HumanTime = None):
        """Show today's or [date]s MLB games with score, status"""
        date = await self.sports_date(ctx, date)
        url = "https://statsapi.mlb.com/api/v1/schedule"
        params = {'sportId': 1, 'hydrate': 'linescore,team', 
                  'startDate': str(date.date()), 'endDate': str(date.date())}
        async with self.bot.session.get(url, params=params) as resp:
            data = await resp.json()
            if not data['dates']:
                await ctx.send(f"No games found for {date.date()}")
                return
            data = data['dates'][0]['games']
        games = []
        for game in data:
            home = game['teams']['home']
            away = game['teams']['away']
        #    if away['team']['id'] not in self.MLB_TEAMS and home['team']['id'] not in self.MLB_TEAMS:
         #       continue
            code = game['status']['codedGameState']
            if code == "I" or code == "F" or code == "O":
                # In progress, Final/Over (whatever the difference is...)
                status = "Final"
                if code == "I":
                     status = "{} {}".format(game['linescore']['inningState'],
                                            self.bot.utils.ordinal(game['linescore']['currentInning']))
                
                o = "{} {} - {} {} | {}".format(
                                        away['team']['teamName'].ljust(9),
                                        str(away['score']).rjust(2),
                                        str(home['score']).ljust(2),
                                        home['team']['teamName'].ljust(9),
                                        status)
            
            elif code == "S" or code == "P":
                #Scheduled
                starttime = datetime.datetime.strptime(game['gameDate'], "%Y-%m-%dT%H:%M:%SZ")
                starttime = starttime.replace(tzinfo=pytz.utc).astimezone(tz=date.tzinfo)
                tzname = starttime.tzname()
                starttime = starttime.strftime('%I:%M%p').lstrip('0').replace(':00', '')

                o = "{} @    {} | {} {}".format(
                                            away['team']['teamName'].ljust(12),
                                            home['team']['teamName'].ljust(9),
                                            starttime, tzname)
            else:
                continue
            
            games.append(o)

        if games:
            await ctx.send("```{}```".format("\n".join(games)))
        else:
            await ctx.send(f"No games found for {date.date()}")


    @commands.command()
    async def nba(self, ctx, *, date: HumanTime = None):
        """Show today's or [date]s NBA games with score, status"""
        todaydate = await self.sports_date(ctx, None)
        date = await self.sports_date(ctx, date)
        if date.date() == todaydate.date():
            url = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
            today = True
        else:
            url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
            today = False
        
        async with self.bot.session.get(url) as resp:
            data = await resp.json(content_type=None)

        if today:
            data = data['scoreboard']
            startkey = 'gameTimeUTC'
        else:
            days = data['leagueSchedule']['gameDates']
            for gameday in days:
                day = datetime.datetime.strptime(gameday['gameDate'], "%m/%d/%Y %H:%M:%S")
                if day.date() == date.date():
                    data = gameday
            startkey = 'gameDateTimeUTC'
            if 'games' not in data:
                await ctx.send(f"No games found for {date.date()}")
                return

       
        games = []
        for game in data['games']:
            starttime = datetime.datetime.strptime(game[startkey], "%Y-%m-%dT%H:%M:%SZ")
            starttime = starttime.replace(tzinfo=pytz.utc).astimezone(tz=date.tzinfo)
            if starttime.date() != date.date():
                continue

            home = game['homeTeam']
            away = game['awayTeam']
            status = game['gameStatusText']

            homet = home['teamName'].ljust(13)
            awayt = away['teamName'].ljust(13)
            if game['gameStatus'] == 1:
                gstart = starttime.strftime('%-I:%M%p').replace(':00', '')
                out = f"{awayt}     @     {homet} | {gstart} {date.tzname()}"
                if 'seriesText' in game:
                    out += f" - {game['seriesText']}"
            else:
                ascore = str(away['score']).rjust(3)
                hscore = str(home['score']).ljust(3)
                out = f"{awayt} {ascore} - {hscore} {homet} | {status}"

            games.append(out)
        
        if games:
            await ctx.send("```{}```".format("\n".join(games)))
        else:
            await ctx.send(f"No games found for {date.date()}")


		
    @commands.command()
    async def nhl(self, ctx, *, date: HumanTime = None):
        """Show today's or [date]s NHL games with score, status"""
        date = await self.sports_date(ctx, date)

        url = "http://statsapi.web.nhl.com/api/v1/schedule"
        par = {'startDate': str(date.date()), 'endDate': str(date.date()),
               'expand': "schedule.teams,schedule.linescore,schedule.game.seriesSummary"}
        
        async with self.bot.session.get(url, params=par) as resp:
            data = await resp.json()
            
        games = []
        if not data['dates']:
            await ctx.send(f"No games found for {date.date()}")
            return
        
        for game in data['dates'][0]['games']:
            gamestatus = game['status']['statusCode'] 
            if gamestatus == "1" or gamestatus == "2" or gamestatus == "9" or gamestatus == "8":
                # game is scheduled in future
                starttime = datetime.datetime.strptime(game['gameDate'], "%Y-%m-%dT%H:%M:%SZ")
                starttime = starttime.replace(tzinfo=pytz.utc).astimezone(tz=date.tzinfo)
                tzname = starttime.tzname()
                starttime = starttime.strftime('%I:%M%p').lstrip('0').replace(':00', '')
                if gamestatus == "8":
                    starttime = "TBD"

                gametxt = "{} @    {} | {} {}".format(
                    game['teams']['away']['team']['teamName'].ljust(17),
                    game['teams']['home']['team']['teamName'].ljust(14),
                    starttime, tzname)
                if gamestatus == "9":
                    gametxt += " Postponed"
                if str(game['gamePk'])[4:6] == "03":
                    gametxt += f" - {game['seriesSummary']['seriesStatusShort']}"
            else:
                # game finished or currently on
                away = '{} {}'.format(
                    game['teams']['away']['team']['teamName'].ljust(14),
                    str(game['linescore']['teams']['away']['goals']).rjust(2))
                
                home = '{} {}'.format(
                    str(game['linescore']['teams']['home']['goals']).ljust(2),
                    game['teams']['home']['team']['teamName'].ljust(14))
                                    
                status = '{} {}'.format(
                    game['linescore']['currentPeriodTimeRemaining'],
                    game['linescore']['currentPeriodOrdinal'])
                                        
                if game['status']['statusCode'] == "7":
                    status = status.replace("3rd", "").strip()
                    
                gametxt = "{} - {} | {}".format(away, home, status)
                
            games.append(gametxt)
        
        if games:
            await ctx.send("```{}```".format("\n".join(games)))


    @commands.command(aliases=['cfl', 'xfl'])
    async def nfl(self, ctx, *, date: HumanTime = None):
        """Show today's NFL games with score, status
           While a date can be provided the API is weird and only works for the current week?"""

        url = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'
        if ctx.invoked_with.lower() == "cfl":
            url = 'https://site.api.espn.com/apis/site/v2/sports/football/cfl/scoreboard'
        if ctx.invoked_with.lower() == "xfl":
            url = 'https://site.api.espn.com/apis/site/v2/sports/football/xfl/scoreboard'
        date = await self.sports_date(ctx, date)
        async with self.bot.session.get(url) as resp:
            data = await resp.json()

        games = []
        for game in data['events']:
            starttime = datetime.datetime.strptime(game['date'], "%Y-%m-%dT%H:%MZ")
            starttime = starttime.replace(tzinfo=pytz.utc).astimezone(tz=date.tzinfo)
            if starttime.date() != date.date():
                continue

            home = game['competitions'][0]['competitors'][0]
            away = game['competitions'][0]['competitors'][1]
            status = game['status']['type']['description']


            if status == "Scheduled":
                homet = home['team']['shortDisplayName'].ljust(11)
                awayt = away['team']['shortDisplayName'].ljust(14)
                gstart = starttime.strftime('%-I:%M%p').replace(':00', '')
                out = f"{awayt} @    {homet} | {gstart} {date.tzname()}"
            else:
                homet = home['team']['shortDisplayName'].ljust(11)
                awayt = away['team']['shortDisplayName'].ljust(11)
                ascore = away['score'].rjust(2)
                hscore = home['score'].rjust(2)
                period = self.bot.utils.ordinal(game['status']['period'])
                if status == "In Progress":
                    status = f"{game['status']['displayClock']} {period}"
                else:
                    status = game['status']['type']['detail']
                out = f"{awayt} {ascore} - {hscore} {homet} | {status}"

            games.append(out)

        if games:
            await ctx.send("```{}```".format("\n".join(games)))
        else:
            await ctx.send(f"No games found for {date.date()}")



async def setup(bot):
    await bot.add_cog(Sports(bot))
