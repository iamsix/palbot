import discord
from discord.ext import commands
import datetime
import pytz
from utils.time import HumanTime


class WorldCup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # API-Football endpoints with hardcoded API key
        self.api_base = "https://v3.football.api-sports.io"
        self.world_cup_id = 1  # FIFA World Cup competition ID
        self.api_headers = {
            "X-RapidAPI-Host": "v3.football.api-sports.io",
            "X-RapidAPI-Key": "377e12bf44e50a3e919fd8ac280d7868"
        }
        
    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.errors.CheckFailure):
            return
        else:
            self.bot.logger.info(error)
            print(error)

    async def sports_date(self, ctx, date):
        """Helper function to handle date parsing"""
        if not date:
            if ctx.author_info.timezone:
                return datetime.datetime.now(pytz.timezone(ctx.author_info.timezone))
            else:
                return datetime.datetime.now(pytz.timezone("US/Eastern"))
        else:
            return date.dt
    
    async def worldcup_formatter(self, data, show_date=False):
        """Format World Cup games data for display"""
        out = []
        lmax, rmax = 0, 0
        slen = 1
        
        # Calculate max lengths for formatting
        for g in data:
            if len(g['ateam']) > lmax:
                lmax = len(g['ateam'])
            if len(g['hteam']) > rmax:
                rmax = len(g['hteam'])
            if not g['scheduled']:
                if slen < 2 and (int(g['ascore']) > 9 or int(g['hscore']) > 9):
                    slen = 2
                if slen < 3 and (int(g['ascore']) > 99 or int(g['hscore']) > 99):
                    slen = 3
        
        # Format each game
        for g in data:
            line = ""
            if show_date and 'date' in g:
                line = f"{g['date']} - "
                
            if g['scheduled']:
                line += f"`{g['ateam'].ljust(lmax + slen)}  vs {' ' * slen} {g['hteam'].ljust(rmax)} | {g['status']}`"
            else:
                line += f"`{g['ateam'].ljust(lmax)} {str(g['ascore']).rjust(slen)} - {str(g['hscore']).ljust(slen)} {g['hteam'].ljust(rmax)} | {g['status']}`"
                
            out.append(line)
        
        return out

    @commands.command(aliases=['wc2026', 'wc'])
    async def worldcup(self, ctx, *, date: HumanTime = None):
        """Show World Cup 2026 matches for today or specified date"""
        target_date = await self.sports_date(ctx, date)
        
        # API-Football endpoint for fixtures
        url = f"{self.api_base}/fixtures"
        
        params = {
            'league': self.world_cup_id,  # World Cup league ID
            'season': 2026,  # 2026 season
            'date': target_date.strftime('%Y-%m-%d') if date else None
        }
        
        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}
        
        try:
            async with self.bot.session.get(url, headers=self.api_headers, params=params) as resp:
                if resp.status != 200:
                    if resp.status == 429:
                        await ctx.send("⚽ API rate limit reached. Please try again later.")
                    elif resp.status == 403:
                        await ctx.send("⚽ API access denied. Check API key configuration.")
                    else:
                        await ctx.send(f"⚽ API error ({resp.status}). Please try again later.")
                    return
                    
                data = await resp.json()
                
        except Exception as e:
            await ctx.send(f"⚽ Connection error: {str(e)}")
            return
        
        if not data.get('response'):
            await ctx.send(f"No World Cup matches found for {target_date.date()}")
            return
            
        gdata = []
        
        # Process API-Football response format
        for match in data['response']:
            fixture = match['fixture']
            teams = match['teams']
            goals = match['goals']
            venue = match['fixture']['venue']
            
            home_team = teams['home']['name']
            away_team = teams['away']['name']
            
            # Parse match status
            status = fixture['status']['short']
            
            if status in ['TBD', 'NS', 'PST']:  # Not started
                # Future match
                match_time = datetime.datetime.fromisoformat(fixture['date'].replace('Z', '+00:00'))
                timestamp = f"<t:{int(match_time.timestamp())}:t>"
                if venue and venue['name']:
                    timestamp += f" ({venue['name']})"
                    
                gdata.append({
                    "ateam": away_team,
                    "hteam": home_team,
                    "status": timestamp,
                    "scheduled": True
                })
                
            elif status in ['1H', '2H', 'HT', 'ET', 'P', 'LIVE']:  # Live
                # Live match
                minute = fixture['status']['elapsed'] or 0
                match_status = f"{minute}' {fixture['status']['long']}"
                    
                gdata.append({
                    "ateam": away_team,
                    "ascore": goals['away'] or 0,
                    "hteam": home_team,
                    "hscore": goals['home'] or 0,
                    "status": match_status,
                    "scheduled": False
                })
                
            elif status in ['FT', 'AET', 'PEN']:  # Finished
                # Finished match
                match_status = "Final"
                if status == 'AET':
                    match_status += " AET"
                elif status == 'PEN':
                    match_status += " Pens"
                    
                gdata.append({
                    "ateam": away_team,
                    "ascore": goals['away'] or 0,
                    "hteam": home_team,
                    "hscore": goals['home'] or 0,
                    "status": match_status,
                    "scheduled": False
                })
        
        if gdata:
            out = await self.worldcup_formatter(gdata)
            embed = discord.Embed(
                title="🏆 FIFA World Cup 2026",
                description="\n".join(out),
                color=0x326295
            )
            if len(data['response']) == 50:  # API limit hit
                embed.set_footer(text="Showing first 50 matches")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"No World Cup matches found for {target_date.date()}")

    @commands.command(aliases=['wcschedule', 'wcfixtures'])
    async def worldcupschedule(self, ctx, days: int = 7):
        """Show upcoming World Cup matches for the next N days (default: 7)"""
        if days > 30:
            days = 30  # Limit to reasonable number
            
        start_date = datetime.datetime.now(pytz.UTC)
        end_date = start_date + datetime.timedelta(days=days)
        
        url = f"{self.api_base}/fixtures"
        
        params = {
            'league': self.world_cup_id,
            'season': 2026,
            'from': start_date.strftime('%Y-%m-%d'),
            'to': end_date.strftime('%Y-%m-%d'),
            'status': 'NS'  # Not started (upcoming matches only)
        }
        
        try:
            async with self.bot.session.get(url, headers=self.api_headers, params=params) as resp:
                if resp.status != 200:
                    await ctx.send(f"⚽ API error ({resp.status}). Please try again later.")
                    return
                    
                data = await resp.json()
                
        except Exception as e:
            await ctx.send(f"⚽ Connection error: {str(e)}")
            return
            
        if not data.get('response'):
            await ctx.send(f"No World Cup matches scheduled for the next {days} days")
            return
            
        gdata = []
        for match in data['response']:
            fixture = match['fixture']
            teams = match['teams']
            venue = fixture['venue']
            
            match_time = datetime.datetime.fromisoformat(fixture['date'].replace('Z', '+00:00'))
            timestamp = f"<t:{int(match_time.timestamp())}:R>"
            date_str = match_time.strftime('%m/%d')
            venue_name = venue['name'] if venue and venue['name'] else ''
            
            gdata.append({
                "ateam": teams['away']['name'],
                "hteam": teams['home']['name'],
                "status": f"{timestamp} {venue_name}".strip(),
                "scheduled": True,
                "date": date_str
            })
        
        if gdata:
            out = await self.worldcup_formatter(gdata, show_date=True)
            embed = discord.Embed(
                title=f"🗓️ World Cup Schedule - Next {days} Days",
                description="\n".join(out[:20]),  # Limit to 20 matches
                color=0x326295
            )
            if len(out) > 20:
                embed.set_footer(text=f"Showing first 20 of {len(out)} matches")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"No matches scheduled for the next {days} days")

    @commands.command(aliases=['wcstandings', 'wctable'])
    async def worldcupstandings(self, ctx):
        """Show World Cup group standings"""
        url = f"{self.api_base}/standings"
        
        params = {
            'league': self.world_cup_id,
            'season': 2026
        }
        
        try:
            async with self.bot.session.get(url, headers=self.api_headers, params=params) as resp:
                if resp.status != 200:
                    await ctx.send(f"⚽ API error ({resp.status}). Please try again later.")
                    return
                    
                data = await resp.json()
                
        except Exception as e:
            await ctx.send(f"⚽ Connection error: {str(e)}")
            return
            
        if not data.get('response') or not data['response'][0].get('league', {}).get('standings'):
            await ctx.send("No World Cup standings available yet")
            return
            
        standings = data['response'][0]['league']['standings']
        
        embeds = []
        for group in standings:
            if not group:
                continue
                
            # Determine group name from first team's group
            group_name = f"Group {group[0]['group']}" if group[0]['group'] else "Standings"
            
            standings_text = "```\n"
            standings_text += f"{'Team':<15} {'MP':<3} {'W':<3} {'D':<3} {'L':<3} {'GD':<4} {'Pts':<3}\n"
            standings_text += "-" * 50 + "\n"
            
            for team_data in group:
                team_name = team_data['team']['name'][:14]  # Truncate long names
                stats = team_data['all']
                
                mp = stats['played']
                w = stats['win']
                d = stats['draw']
                l = stats['lose']
                gd = stats['goals']['for'] - stats['goals']['against']
                pts = team_data['points']
                
                standings_text += f"{team_name:<15} {mp:<3} {w:<3} {d:<3} {l:<3} {gd:+<4} {pts:<3}\n"
            
            standings_text += "```"
            
            embed = discord.Embed(
                title=f"🏆 World Cup 2026 - {group_name}",
                description=standings_text,
                color=0x326295
            )
            embeds.append(embed)
        
        # Send first group, could add pagination for multiple groups
        if embeds:
            await ctx.send(embed=embeds[0])
            # If multiple groups, mention it
            if len(embeds) > 1:
                await ctx.send(f"📊 Showing {embeds[0].title}. Use !wcgroup [A-H] for specific groups.")
        else:
            await ctx.send("No standings data available")

    @commands.command(aliases=['wcgroup'])
    async def worldcupgroup(self, ctx, group: str = None):
        """Show specific World Cup group standings (A-H)"""
        if not group:
            await ctx.send("Please specify a group letter (A-H). Example: `!wcgroup A`")
            return
            
        group = group.upper()
        if group not in 'ABCDEFGH':
            await ctx.send("Invalid group. Please use A-H.")
            return
            
        url = f"{self.api_base}/standings"
        
        params = {
            'league': self.world_cup_id,
            'season': 2026
        }
        
        try:
            async with self.bot.session.get(url, headers=self.api_headers, params=params) as resp:
                if resp.status != 200:
                    await ctx.send(f"⚽ API error ({resp.status}). Please try again later.")
                    return
                    
                data = await resp.json()
                
        except Exception as e:
            await ctx.send(f"⚽ Connection error: {str(e)}")
            return
            
        if not data.get('response') or not data['response'][0].get('league', {}).get('standings'):
            await ctx.send(f"No standings available for Group {group}")
            return
            
        standings = data['response'][0]['league']['standings']
        
        # Find the requested group
        target_group = None
        for standing_group in standings:
            if standing_group and standing_group[0]['group'] == group:
                target_group = standing_group
                break
        
        if not target_group:
            await ctx.send(f"Group {group} not found or no data available")
            return
            
        standings_text = "```\n"
        standings_text += f"{'Team':<18} {'MP':<3} {'W':<3} {'D':<3} {'L':<3} {'GF':<3} {'GA':<3} {'GD':<4} {'Pts':<3}\n"
        standings_text += "-" * 65 + "\n"
        
        for i, team_data in enumerate(target_group):
            pos_icon = ["🥇", "🥈", "🥉", "4️⃣"][i] if i < 4 else f"{i+1}."
            team_name = team_data['team']['name'][:16]  # Truncate long names
            stats = team_data['all']
            
            mp = stats['played']
            w = stats['win']
            d = stats['draw']
            l = stats['lose']
            gf = stats['goals']['for']
            ga = stats['goals']['against']
            gd = gf - ga
            pts = team_data['points']
            
            standings_text += f"{pos_icon} {team_name:<15} {mp:<3} {w:<3} {d:<3} {l:<3} {gf:<3} {ga:<3} {gd:+<4} {pts:<3}\n"
        
        standings_text += "```"
        
        embed = discord.Embed(
            title=f"🏆 World Cup 2026 - Group {group}",
            description=standings_text,
            color=0x326295
        )
        embed.set_footer(text="🥇🥈 = Advance to Round of 16")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(WorldCup(bot))