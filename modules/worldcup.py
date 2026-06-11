import discord
from discord.ext import commands
import datetime
import pytz
from utils.time import HumanTime


class WorldCup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # API-Football endpoints
        self.api_base = "https://v3.football.api-sports.io"
        self.world_cup_id = 1  # FIFA World Cup competition ID
        
        # Get API key from config
        if not hasattr(self.bot.config, 'api_football_key'):
            self.bot.logger.error("api_football_key not configured - World Cup module will not work")
            self.api_key = None
        else:
            self.api_key = self.bot.config.api_football_key
            
        self.api_headers = {
            "X-RapidAPI-Host": "v3.football.api-sports.io",
            "X-RapidAPI-Key": self.api_key
        } if self.api_key else {}

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
    @commands.cooldown(3, 86400, commands.BucketType.user)  # 3 per day per user
    async def worldcup(self, ctx, *, date: HumanTime = None):
        """Show World Cup 2026 matches for today or specified date"""
        if not self.api_key:
            await ctx.send("⚽ World Cup module not configured. Contact admin.")
            return
            
        # Use sports.py helper for date parsing
        target_date = await ctx.bot.get_cog('Sports').sports_date(ctx, date)
        
        # API-Football endpoint for fixtures
        url = f"{self.api_base}/fixtures"
        
        params = {
            'league': self.world_cup_id,  # World Cup league ID
            'season': 2026,  # 2026 season
            'date': target_date.strftime('%Y-%m-%d')  # Always include date
        }
        
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
            self.bot.logger.error(f"World Cup API error: {e}")
            await ctx.send("⚽ Connection error. Please try again later.")
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
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"No World Cup matches found for {target_date.date()}")

    @commands.command(aliases=['wcschedule', 'wcfixtures'])
    @commands.cooldown(3, 86400, commands.BucketType.user)  # 3 per day per user
    async def worldcupschedule(self, ctx, days: int = 7):
        """Show upcoming World Cup matches for the next N days (default: 7)"""
        if not self.api_key:
            await ctx.send("⚽ World Cup module not configured. Contact admin.")
            return
            
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
                    if resp.status == 429:
                        await ctx.send("⚽ API rate limit reached. Please try again later.")
                    elif resp.status == 403:
                        await ctx.send("⚽ API access denied. Check API key configuration.")
                    else:
                        await ctx.send(f"⚽ API error ({resp.status}). Please try again later.")
                    return
                    
                data = await resp.json()
                
        except Exception as e:
            self.bot.logger.error(f"World Cup schedule API error: {e}")
            await ctx.send("⚽ Connection error. Please try again later.")
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
    @commands.cooldown(3, 86400, commands.BucketType.user)  # 3 per day per user
    async def worldcupstandings(self, ctx):
        """Show World Cup group standings"""
        if not self.api_key:
            await ctx.send("⚽ World Cup module not configured. Contact admin.")
            return
            
        url = f"{self.api_base}/standings"
        
        params = {
            'league': self.world_cup_id,
            'season': 2026
        }
        
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
            self.bot.logger.error(f"World Cup standings API error: {e}")
            await ctx.send("⚽ Connection error. Please try again later.")
            return
            
        if not data.get('response') or not data['response'][0].get('league', {}).get('standings'):
            await ctx.send("No World Cup standings available yet")
            return
            
        standings = data['response'][0]['league']['standings']
        
        # Build combined view of all groups (limited to avoid Discord limits)
        all_groups_text = ""
        group_count = 0
        
        for group in standings:
            if not group:
                continue
                
            group_name = group[0]['group'] if group[0]['group'] else "?"
            group_text = f"**Group {group_name}**\n```\n"
            group_text += f"{'Team':<14} {'MP':<2} {'W':<2} {'D':<2} {'L':<2} {'GD':<4} {'Pts':<3}\n"
            
            for team_data in group[:4]:  # Top 4 teams only
                team_name = team_data['team']['name'][:14]  # Truncate long names
                stats = team_data['all']
                
                mp = stats['played']
                w = stats['win']
                d = stats['draw']
                l = stats['lose']
                gd = stats['goals']['for'] - stats['goals']['against']
                pts = team_data['points']
                
                group_text += f"{team_name:<14} {mp:<2} {w:<2} {d:<2} {l:<2} {gd:>+4} {pts:<3}\n"
            
            group_text += "```\n"
            
            # Check if adding this group would exceed Discord limit
            if len(all_groups_text + group_text) > 3500:  # Leave room for embed title/footer
                break
                
            all_groups_text += group_text
            group_count += 1
            
            if group_count >= 6:  # Limit groups to avoid spam
                break
        
        if all_groups_text:
            embed = discord.Embed(
                title="🏆 FIFA World Cup 2026 - Group Standings",
                description=all_groups_text,
                color=0x326295
            )
            embed.set_footer(text=f"Showing {group_count} groups • Use !wcgroup [A-L] for specific groups")
            await ctx.send(embed=embed)
        else:
            await ctx.send("No standings data available")

    @commands.command(aliases=['wcgroup'])
    @commands.cooldown(3, 86400, commands.BucketType.user)  # 3 per day per user
    async def worldcupgroup(self, ctx, group: str = None):
        """Show specific World Cup group standings (A-L)"""
        if not self.api_key:
            await ctx.send("⚽ World Cup module not configured. Contact admin.")
            return
            
        if not group:
            await ctx.send("Please specify a group letter (A-L). Example: `!wcgroup A`")
            return
            
        group = group.upper()
        if group not in 'ABCDEFGHIJKL':  # WC2026 has 12 groups (A-L)
            await ctx.send("Invalid group. Please use A-L for World Cup 2026.")
            return
            
        url = f"{self.api_base}/standings"
        
        params = {
            'league': self.world_cup_id,
            'season': 2026
        }
        
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
            self.bot.logger.error(f"World Cup group API error: {e}")
            await ctx.send("⚽ Connection error. Please try again later.")
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
        standings_text += f"{'Team':<16} {'MP':<3} {'W':<3} {'D':<3} {'L':<3} {'GF':<3} {'GA':<3} {'GD':<4} {'Pts':<3}\n"
        standings_text += "-" * 65 + "\n"
        
        for i, team_data in enumerate(target_group):
            # Position indicators without emoji to preserve monospace
            pos_num = f"{i+1}."
            team_name = team_data['team']['name'][:14]  # Consistent truncation
            stats = team_data['all']
            
            mp = stats['played']
            w = stats['win']
            d = stats['draw']
            l = stats['lose']
            gf = stats['goals']['for']
            ga = stats['goals']['against']
            gd = gf - ga
            pts = team_data['points']
            
            standings_text += f"{pos_num:<3}{team_name:<14} {mp:<3} {w:<3} {d:<3} {l:<3} {gf:<3} {ga:<3} {gd:>+4} {pts:<3}\n"
        
        standings_text += "```"
        
        embed = discord.Embed(
            title=f"🏆 World Cup 2026 - Group {group}",
            description=standings_text,
            color=0x326295
        )
        # Fixed footer for WC2026 format (32-team tournament with different advancement)
        embed.set_footer(text="Top 2 teams + 8 best 3rd-place teams advance to Round of 32")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(WorldCup(bot))
