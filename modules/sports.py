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
#                                        away['team']['abbreviation'].ljust(3),
                                        str(away['score']).rjust(2),
                                        str(home['score']).ljust(2),
                                        home['team']['teamName'].ljust(9),
#                                        home['team']['abbreviation'].ljust(3),
                                        status)
            
            elif code == "S" or code == "P":
                #Scheduled
                starttime = datetime.datetime.strptime(game['gameDate'], "%Y-%m-%dT%H:%M:%SZ")
                starttime = starttime.replace(tzinfo=pytz.utc).astimezone(tz=date.tzinfo)
                tzname = starttime.tzname()
                starttime = starttime.strftime('%I:%M%p').lstrip('0').replace(':00', '')

                o = "{} @    {} | {} {}".format(
#                                            away['team']['abbreviation'].ljust(3),
                                            away['team']['teamName'].ljust(12),
                                            home['team']['teamName'].ljust(9),
#                                            home['team']['abbreviation'].ljust(3),
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
        if 'games' not in data or not data['games']:
            await ctx.send(f"No games found for {date.date()}")
            return

        e = discord.Embed()
        for game in data['games']:
            starttime = datetime.datetime.strptime(game[startkey], "%Y-%m-%dT%H:%M:%SZ")
            starttime = f"<t:{int(starttime.timestamp())}:t>"

            home = game['homeTeam']
            away = game['awayTeam']
            status = game['gameStatusText'].strip()
            series = ""
            if 'seriesText' in game and game['seriesText']:
                    series = game['seriesText']

            homet = home['teamName'].rjust(13)
            awayt = away['teamName'].ljust(13)
            if game['gameStatus'] == 1:
                e.add_field(name=f"`{awayt}     @     {homet}`", 
                            value=f"{starttime}`{series.rjust(29)}`", inline=False)
                
            else:
                ascore = str(away['score']).rjust(3)
                hscore = str(home['score']).ljust(3)

                e.add_field(name=f"`{awayt} {ascore} - {hscore} {homet}`", 
                            value=f"`{status.ljust(12)}{series.rjust(25)}`", inline=False)
               
        
        await ctx.send(embed=e)


    NHL_TEAM_NAMES = {"Maple Leafs": "Leafs", 
                      "Blue Jackets": "B Jackets", 
                      "Golden Knights": "G Knights",
                      }
    def short_nhl_name(self, name):
        if name in self.NHL_TEAM_NAMES:
            return self.NHL_TEAM_NAMES[name]
        else:
            return name
		
    @commands.command()
    async def nhl(self, ctx, *, date: HumanTime = None):
        """Show today's or [date]s NHL games with score, status"""
        date = await self.sports_date(ctx, date)

        url = "https://api-web.nhle.com/v1/score/" + str(date.date())
        
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            
        games = []
        if not data['games']:
            await ctx.send(f"No games found for {date.date()}")
            return
        
        e = discord.Embed()
        
        for game in data['games']:
            gamestatus = game['gameState'] 
            home = self.short_nhl_name(game['homeTeam']['name']['default'])
            away = self.short_nhl_name(game['awayTeam']['name']['default'])

            # Might need to use 'gameScheduleState' at some point
            if gamestatus == "PRE" or gamestatus == "FUT":
                # game is scheduled in future
                starttime = datetime.datetime.strptime(game['startTimeUTC'], "%Y-%m-%dT%H:%M:%SZ")
                starttime = f"<t:{int(starttime.timestamp())}:t>"

                status = ""
                if 'seriesStatus' in game and game['seriesStatus']:
                    status = f"{self.parse_nhl_playoff(game)}"

                e.add_field(name=f"`{away.ljust(13)} @    {home.rjust(10)}`", 
                            value=f"{starttime}`{status.rjust(21)}`", inline=False)

            else:
                # "LIVE" for on. "OFF" for finished?
                # game finished or currently on
                away = '{} {}'.format(
                    away.ljust(10),
                    str(game['awayTeam']['score']).rjust(2))
                
                home = '{} {}'.format(
                    str(game['homeTeam']['score']).ljust(2),
                    home.rjust(10))
                                    
                # Check ['clock']['running']?

                status = '{} {}'.format(
                    game['clock']['timeRemaining'],
                    self.bot.utils.ordinal(game['period']))
                if game['clock']['inIntermission']:
                    status = f"{self.bot.utils.ordinal(game['period'])} Int"
                # ['periodDescriptor']['periodType'] shows OT?
                                        
                if gamestatus == "OFF":   
                    status = "Final"
                    if game['gameOutcome']['lastPeriodType'] == "OT":
                        status += " OT"

                if 'seriesStatus' in game and game['seriesStatus']:
                    status = status.ljust(12) + f"{self.parse_nhl_playoff(game).rjust(17)}"
                
                e.add_field(name=f"`{away} - {home}`", value=f"`{status.ljust(29)}`", inline=False)
        
        await ctx.send(embed=e)

    def parse_nhl_playoff(self, game):
        tscore = game['seriesStatus']['topSeedWins']
        bscore = game['seriesStatus']['bottomSeedWins']
       # gmnum = game['seriesStatus']['gameNumberOfSeries']

        if tscore > bscore:
            wscore = tscore
            lscore = bscore
            winner = game['seriesStatus']['topSeedTeamAbbrev']
        else:
            wscore = bscore
            lscore = tscore
            if wscore == lscore:
                winner = "TIED"
            else:
                winner = game['seriesStatus']['bottomSeedTeamAbbrev']
        leads = "leads"
        if wscore == 4:
            leads = "wins"
        elif winner == "TIED":
            leads = ""

        return f"{winner} {leads} {wscore}-{lscore}"


    @commands.command(aliases=['cfl', 'xfl', 'ufl'])
    async def nfl(self, ctx, *, date: HumanTime = None):
        """Show today's NFL games with score, status
           While a date can be provided the API is weird and only works for the current week?"""

        url = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'
        if ctx.invoked_with.lower() == "cfl":
            url = 'https://site.api.espn.com/apis/site/v2/sports/football/cfl/scoreboard'
        if ctx.invoked_with.lower() == "xfl":
            url = 'https://site.api.espn.com/apis/site/v2/sports/football/xfl/scoreboard'
        if ctx.invoked_with.lower() == "ufl":
            url = 'https://site.api.espn.com/apis/site/v2/sports/football/ufl/scoreboard'
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
