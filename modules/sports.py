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
        
    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.errors.CheckFailure):
            return
        else:
            self.bot.logger.info(error)

        
    async def sports_formatter(self, data):
        out = []
        lmax, rmax = 0, 0
        slen = 1
        for g in data:
            if len(g['ateam']) > lmax:
                lmax = len(g['ateam'])
            if len(g['hteam']) > rmax:
                rmax = len(g['hteam'])
            if not g['scheduled']:
                if slen < 2 and (int(g['ascore']) > 10 or int(g['hscore']) > 10):
                    slen = 2
                if slen < 3 and (int(g['ascore']) > 100 or int(g['hscore']) > 100):
                    slen = 3
        
        for g in data:
            if g['scheduled']:
                out.append(f"`{g['ateam'].ljust(lmax + slen)}  @ {" " * slen} {g['hteam'].ljust(rmax)} |`{g['status']}")
            else:
                out.append(f"`{g['ateam'].ljust(lmax)} {str(g['ascore']).rjust(slen)} - {str(g['hscore']).ljust(slen)} {g['hteam'].ljust(rmax)} | {g['status']}`")

        return out

    @commands.command() 
    async def nhlt(self, ctx, *, date: HumanTime = None):
        """Test command of a self-updating scoreboard"""
        post = await ctx.send("testing")
        await asyncio.sleep(1)
        await post.add_reaction("\N{HIGH VOLTAGE SIGN}")
        for repeat in range(10):
            data = await self.nhl(ctx, date=date, test=True)
            out = await self.sports_formatter(data)
            await post.edit(content="\n".join(out))
            await asyncio.sleep(30)
        await post.clear_reaction("\N{HIGH VOLTAGE SIGN}")


    async def sports_channel(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.invoked_with == "help":
            return True
        if  (ctx.guild and ctx.guild.id == 124572142485504002) and ctx.channel.id != 1243723119567310858:
            msg = await ctx.reply(f"`!{ctx.invoked_with}` is stored in the <#1243723119567310858>. This message will self destruct.")
            await asyncio.sleep(5)
            await msg.delete()

            return False
        else:
            return True



    @commands.check(sports_channel)
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
        gdata = []
        for game in data:
            home = game['teams']['home']
            away = game['teams']['away']

            code = game['status']['codedGameState']
            if code == "I" or code == "F" or code == "O":
                # In progress, Final/Over (whatever the difference is...)
                status = "Final"
                if code == "I":
                     status = "{} {}".format(game['linescore']['inningState'],
                                            self.bot.utils.ordinal(game['linescore']['currentInning']))
                
                gdata.append({"ateam": away['team']['teamName'], 
                            "ascore": away['score'],
                            "hteam": home['team']['teamName'],
                            "hscore": home['score'],
                            "status": status, 
                            "scheduled": False})
            
            elif code == "S" or code == "P":
                #Scheduled
                starttime = datetime.datetime.strptime(game['gameDate'], "%Y-%m-%dT%H:%M:%SZ")
                starttime = f"<t:{int(starttime.timestamp())}:t>"

                gdata.append({"ateam": away['team']['teamName'], 
                            "hteam": home['team']['teamName'], 
                            "status": starttime, 
                            "scheduled": True})
            else:
                continue

        if gdata:
            out = await self.sports_formatter(gdata)
            await ctx.send("\n".join(out))
        else:
            await ctx.send(f"No games found for {date.date()}")


    @commands.check(sports_channel)
    @commands.command(aliases=['wnba'])
    async def nba(self, ctx, *, date: HumanTime = None):
        """Show today's or [date]s NBA games with score, status"""
        todaydate = await self.sports_date(ctx, None)
        date = await self.sports_date(ctx, date)
        if date.date() == todaydate.date():
            if ctx.invoked_with.lower() == "wnba":
                url = "https://cdn.wnba.com/static/json/liveData/scoreboard/todaysScoreboard_10.json"
            else:
                url = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
            today = True
        else:
            if ctx.invoked_with.lower() == "wnba":
                url = "https://cdn.wnba.com/static/json/staticData/scheduleLeagueV2.json"
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

        #e = discord.Embed()
        gdata = []
        for game in data['games']:
            starttime = datetime.datetime.strptime(game[startkey], "%Y-%m-%dT%H:%M:%SZ")
            starttime = f"<t:{int(starttime.timestamp())}:t>"

            home = game['homeTeam']
            away = game['awayTeam']
            status = game['gameStatusText'].strip()
            # series = ""
            # if 'seriesText' in game and game['seriesText']:
            #         series = game['seriesText']

            homet = home['teamName']
            awayt = away['teamName']
            if game['gameStatus'] == 1:
                gdata.append({"ateam": awayt, 
                            "hteam": homet, 
                            "status": starttime, 
                            "scheduled": True})
                
            else:
                gdata.append({"ateam": awayt, 
                            "ascore": away['score'],
                            "hteam": homet,
                            "hscore": home['score'],
                            "status": status, 
                            "scheduled": False})
               
        out = await self.sports_formatter(gdata)
        await ctx.send("\n".join(out))


    NHL_TEAM_NAMES = {"Maple Leafs": "Leafs", 
                      "Blue Jackets": "B Jackets", 
                      "Golden Knights": "G Knights",
                      "Utah Hockey Club": "Utah",
                      }
    def short_nhl_name(self, name):
        if name in self.NHL_TEAM_NAMES:
            return self.NHL_TEAM_NAMES[name]
        else:
            return name
        
    @commands.check(sports_channel)
    @commands.command()
    async def ncaa(self, ctx, *, date: HumanTime = None):
        """Show today's or [date]s NCAA games with score, status"""
        date = await self.sports_date(ctx, date)
        url = "https://data.ncaa.com/casablanca/scoreboard/basketball-men/d1/{}/{:02d}/{:02d}/scoreboard.json"
        url = url.format(date.year, date.month, date.day)
        async with self.bot.session.get(url) as resp:
            data = await resp.json()

        if not data['games']:
            await ctx.send(f"No games found for {date.date()}")
            return
        
        gdata = []
    
        for game in data['games']:
            game = game['game']
            gamestatus = game['gameState']
            home = game['home']['names']['short']
            away = game['away']['names']['short']

            if gamestatus == "pre":
                starttime = f"<t:{game['startTimeEpoch']}:t>"
                gdata.append({"ateam": away, 
                            "hteam": home, 
                            "status": starttime, 
                            "scheduled": True})
                
            else:
                status = '{} {}'.format(
                    game['contestClock'],
                    game['currentPeriod'])
                
                gdata.append({"ateam": away, 
                            "ascore": game['away']['score'],
                            "hteam": home,
                            "hscore": game['home']['score'],
                            "status": status, 
                            "scheduled": False})

        out = await self.sports_formatter(gdata)
        await ctx.send("\n".join(out))
	
    @commands.check(sports_channel)
    @commands.command()
    async def nhl(self, ctx, *, date: HumanTime = None, test=False):
        """Show today's or [date]s NHL games with score, status"""
        date = await self.sports_date(ctx, date)

        url = "https://api-web.nhle.com/v1/score/" + str(date.date())
        
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            
        games = []
        if not data['games']:
            await ctx.send(f"No games found for {date.date()}")
            return
        
        #e = discord.Embed()
        gdata = []
        
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

                gdata.append({"ateam": away, 
                            "hteam": home, 
                            "status": starttime, 
                            "scheduled": True})

            else:                                    
                # Check ['clock']['running']?

                status = '{} {}'.format(
                    game['clock']['timeRemaining'],
                    self.bot.utils.ordinal(game['period']))
                if game['clock']['inIntermission']:
                    status = f"{self.bot.utils.ordinal(game['period'])} Int"
                # ['periodDescriptor']['periodType'] shows OT?
                                        
                if gamestatus == "OFF" or gamestatus == "FINAL":   
                    status = "Final"
                    if game['gameOutcome']['lastPeriodType'] == "OT":
                        status += " OT"

                #if 'seriesStatus' in game and game['seriesStatus']:
                #    status = status.ljust(12) + f"{self.parse_nhl_playoff(game).rjust(17)}"
                
                gdata.append({"ateam": away, 
                            "ascore": game['awayTeam']['score'],
                            "hteam": home,
                            "hscore": game['homeTeam']['score'],
                            "status": status, 
                            "scheduled": False})

        if test:
            return gdata
        out = await self.sports_formatter(gdata)
        await ctx.send("\n".join(out))

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

    @commands.check(sports_channel)
    @commands.command(aliases=['cfl', 'xfl', 'ufl', 'cfb'])
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
        if ctx.invoked_with.lower() == "cfb":
            url = 'https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard'
        date = await self.sports_date(ctx, date)
        async with self.bot.session.get(url) as resp:
            data = await resp.json()

        gdata = []
        for game in data['events']:
            starttime = datetime.datetime.strptime(game['date'], "%Y-%m-%dT%H:%MZ")
            starttime = starttime.replace(tzinfo=pytz.utc).astimezone(tz=date.tzinfo)
            if starttime.date() != date.date():
                continue
            starttime = f"<t:{int(starttime.timestamp())}:t>"

            home = game['competitions'][0]['competitors'][0]
            away = game['competitions'][0]['competitors'][1]
            status = game['status']['type']['description']


            if status == "Scheduled":
                gdata.append({"ateam": away['team']['shortDisplayName'], 
                            "hteam": home['team']['shortDisplayName'], 
                            "status": starttime, 
                            "scheduled": True})
            else:
                period = self.bot.utils.ordinal(game['status']['period'])
                if status == "In Progress":
                    status = f"{game['status']['displayClock']} {period}"
                else:
                    status = game['status']['type']['detail']
                    
                gdata.append({"ateam": away['team']['shortDisplayName'],
                            "ascore": away['score'],
                            "hteam": home['team']['shortDisplayName'],
                            "hscore": home['score'],
                            "status": status, 
                            "scheduled": False})

        if gdata:
            out = await self.sports_formatter(gdata)
            await ctx.send("\n".join(out))
        else:
            await ctx.send(f"No games found for {date.date()}")



async def setup(bot):
    await bot.add_cog(Sports(bot))
