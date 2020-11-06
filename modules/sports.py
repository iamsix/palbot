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

    NBA_TEAMS = {
        "ATL" : "Hawks",
        "BOS" : "Celtics",
        "BKN" : "Nets",
        "CHA" : "Hornets",
        "CHI" : "Bulls",
        "CLE" : "Cavaliers",
        "DAL" : "Mavericks",
        "DEN" : "Nuggets",
        "DET" : "Pistons",
        "GSW" : "Warriors",
        "HOU" : "Rockets",
        "IND" : "Pacers",
        "LAC" : "Clippers",
        "LAL" : "Lakers",
        "MEM" : "Grizzlies",
        "MIA" : "Heat",
        "MIL" : "Bucks",
        "MIN" : "Timberwolves",
        "NOP" : "Pelicans",
        "NYK" : "Knicks",
        "OKC" : "Thunder",
        "ORL" : "Magic",
        "PHI" : "Sixers",
        "PHX" : "Suns",
        "POR" : "Trail Blazers",
        "SAC" : "Kings",
        "SAS" : "Spurs",
        "TOR" : "Raptors",
        "UTA" : "Jazz",
        "WAS" : "Wizards"
    }

    @commands.command()
    async def nba(self, ctx, *, date: HumanTime = None):
        """Show today's or [date]s NBA games with score, status"""
        # TODO Make this use timezone - NBA USES PREFORMATTED STRING CURRENTLY

        def team(arg):
            return self.NBA_TEAMS.get(arg, arg)
        date = await self.sports_date(ctx, date)

        url = "https://data.nba.net/prod/v2/{}/scoreboard.json"
        url = url.format(date.strftime("%Y%m%d"))
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
        
        games = []
        for game in data['games']:
            
            if game['statusNum'] == 1:
                # Game is scheduled in the future
                # TODO localize startTimeUTC  "2019-10-25T23:00:00.000Z"
                gametxt = "{} @     {} | {}"
                gametxt = gametxt.format(
                        team(game['vTeam']['triCode']).ljust(17),
                        team(game['hTeam']['triCode']).ljust(13),
                        game['startTimeEastern'].replace(':00', ''))
    
            else:
                # game is finished or currently on
                gametxt = "{} {} - {} {} | {}"
                if game['statusNum'] == 2: 
                    status = "{} Q{}".format(game['clock'], game['period']['current'])
                else:
                    status = "Final"
                    
                gametxt = gametxt.format(
                        team(game['vTeam']['triCode']).ljust(13),
                        str(game['vTeam']['score']).rjust(3),
                        str(game['hTeam']['score']).ljust(3),
                        team(game['hTeam']['triCode']).ljust(13),
                        status)
            games.append(gametxt)
        
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
               'expand': "schedule.teams,schedule.linescore"}
        
        async with self.bot.session.get(url, params=par) as resp:
            data = await resp.json()
            
        games = []
        if not data['dates']:
            await ctx.send(f"No games found for {date.date()}")
            return
        
        for game in data['dates'][0]['games']:
            gamestatus = game['status']['statusCode'] 
            if gamestatus == "1" or gamestatus == "2" or gamestatus == "9":
                # game is scheduled in future
                starttime = datetime.datetime.strptime(game['gameDate'], "%Y-%m-%dT%H:%M:%SZ")
                starttime = starttime.replace(tzinfo=pytz.utc).astimezone(tz=date.tzinfo)
                tzname = starttime.tzname()
                starttime = starttime.strftime('%I:%M%p').lstrip('0').replace(':00', '')

                gametxt = "{} @    {} | {} {}".format(
                    game['teams']['away']['team']['teamName'].ljust(17),
                    game['teams']['home']['team']['teamName'].ljust(14),
                    starttime, tzname)
                if gamestatus == "9":
                    gametxt += " Postponed"
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


    @commands.command()
    async def nfl(self, ctx, *, date: HumanTime = None):
        """Show today's NFL games with score, status
           While a date can be provided the API is weird and only works for the current week?"""

        date = await self.sports_date(ctx, date)
        r = {'url' : 'https://api.nfl.com/v1/reroute',
            'data' : {'grant_type': 'client_credentials'},
            'headers' : {'x-domain-id': '100'}}

        async with self.bot.session.post(**r) as resp:
            data = await resp.json()
            access_token = data['access_token']

        url = ("https://api.nfl.com/v1/games"
                        "?fs={id,gameTime,gameStatus,"
                        "homeTeam{id,abbr,nickName},visitorTeam{id,abbr,nickName},"
                        "homeTeamScore,visitorTeamScore}")
        
        r = {'url': url, 'headers': {'authorization': 'Bearer ' + access_token}, 'timeout': 3}

        async with self.bot.session.get(**r) as resp:
            data = await resp.json()
        games = []
        for game in data['data']:
            starttime = datetime.datetime.strptime(game['gameTime'][:-3]+"00",
                                        "%Y-%m-%dT%H:%M:%S.%f%z")
            if starttime.date() != date.date():
                continue
            phase = game['gameStatus']['phase']

            if phase == "PREGAME":
                # 2019-08-01T17:00:00.000-07:00 note the improper : in the GMT offset
                starttime = datetime.datetime.strptime(game['gameTime'][:-3]+"00",
                                                "%Y-%m-%dT%H:%M:%S.%f%z")
                starttime = starttime.astimezone(tz=date.tzinfo)
                starttime = starttime.strftime('%-I:%M%p').replace(':00', '')
                out = "{} @    {} | {} {}".format(
                        game['visitorTeam']['nickName'].ljust(16),
                        game['homeTeam']['nickName'].ljust(13),
                        starttime, date.tzname())
            
            else:
                if game['gameStatus']['phase'] == "INGAME":
                    status = "{} Q{}".format(game['gameStatus']['gameClock'],
                                            game['gameStatus']['period'])
                else:
                    status = game['gameStatus']['phase']

                fmt = "{} {} - {} {} | {}"
                out = fmt.format(game['visitorTeam']['nickName'].ljust(13),
                        str(game['visitorTeamScore']['pointsTotal']).rjust(2),
                        str(game['homeTeamScore']['pointsTotal']).ljust(2),
                        game['homeTeam']['nickName'].ljust(13),
                        status)


            games.append(out)

        if games:
            await ctx.send("```{}```".format("\n".join(games)))



def setup(bot):
    bot.add_cog(Sports(bot))
