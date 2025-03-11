import discord
from discord import app_commands
from discord.ext import commands

import datetime
import time


class Strava(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.token = self.bot.config.stravaToken
        self.ctx_menu = app_commands.ContextMenu(name='Strava', callback=self.strava_ctx)
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu)
        pass

    async def strava_ctx(self, interaction: discord.Interaction, user: discord.User):
        userinfo = interaction.client.utils.AuthorInfo(user)
        if userinfo.strava:
            athlete = userinfo.strava_athlete
            if not athlete:
                    athlete = await self.strava_get_athlete_info(user) 
                    if athlete: 
                        athlete['timestamp'] = datetime.datetime.now().timestamp()
                    userinfo.strava_athlete = athlete
            await interaction.response.defer()
            output = await self.do_strava_get(userinfo.strava, 
                                              athlete=userinfo.strava_athlete)
            await interaction.followup.send(output)
        else:
            await interaction.response.send_message(
                f"Sorry {user.display_name} doesn't have a strava user set up.")

    @commands.group(name="strava", case_insensitive=True, invoke_without_command=True)
    async def _strava(self, ctx, user: int = 0):
        """Show your most recent ride from strava.com
           Optionally provide a [user] ID to show the most recent ride of
           use `set strava <id>` to set your strava ID"""

        index = 0
        if user < 0:
            index = abs(user)
            user = ctx.author_info.strava or 0
        else:
            user = user or ctx.author_info.strava
            athlete = ctx.author_info.strava_athlete
            if not athlete:
                    athlete = await self.strava_get_athlete_info(user)
                    if athlete: 
                        athlete['timestamp'] = datetime.datetime.now().timestamp()
                    ctx.author_info.strava_athlete = athlete
        output = ""
        if user:
            output = await self.do_strava_get(user, 
                                              index=index, 
                                              athlete=ctx.author_info.strava_athlete)
        else:
            output = (f"Sorry {ctx.author.mention}, you don't have a Strava ID setup yet, "
                      f"use `{ctx.prefix}set strava <id>` to set one."
                      "Remember, if it's not on Strava, it didn't happen.")
        
        if output:
            await ctx.send(output)

    @_strava.command(name='set')
    async def _strava_set(self, ctx, user: int):
        ctx.author_info.strava = str(user)
        await ctx.send(f"{ctx.author.mention} strava ID set to: {user}, now go ride bikes!")
    @_strava_set.error
    async def _set_strava_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("Failed to set user ID - it should be the number on your profile page URL\n"
                           "For example: <https://www.strava.com/athletes/6188> your ID would be `6188`")
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(error)
    
    @_strava.command(name="activity")
    async def check_activity(self, ctx, activity: int):
        recent_ride = await self.strava_get_ride_extended_info(activity)
        user = recent_ride['athlete']['id']
        if recent_ride:
            athlete = await self.strava_get_athlete_info(user)
            out = await self.parse_strava_ride(recent_ride, athlete)
            await ctx.send(out)


    async def do_strava_get(self, user: int, *, index: int = 0, athlete = None):
        # Process a last ride request for a specific strava id.
        url = f"https://m.strava.com/api/v3/feed/athlete/{user}"
        headers = {'Authorization': 'access_token ' + self.token}
        data = None
        async with self.bot.session.get(url, headers=headers) as resp:
            if resp.status != 200:
                print(await resp.read())
                return f"Unable to retrieve rides from Strava ID: {user}"
            else:
                data = await resp.json()
        if data:
            rides = []
            for ride in data:
                if ride['item']['entity_type'] == "Activity":
                    rides.append(ride['item'])
            recent_ride = await self.strava_get_ride_extended_info(rides[index]['id'])
            if recent_ride:
                self.bot.logger.debug(recent_ride)
                return await self.parse_strava_ride(recent_ride, athlete)
            else:
                return f"Sorry {user}, an error has occured attempting to retrieve the most recent ride's details"
        else:
            return f"Sorry {user}, no rides have been recorded yet. Remember, if it's not on Strava, it didn't happen."



    async def parse_strava_ride(self, recent_ride, athlete=None):
        #if the athlete ID is missing we can default to mph

        self.bot.logger.debug("Strava recent ride:", recent_ride)
        moving_time = str(datetime.timedelta(seconds=recent_ride['moving_time']))
        ride_datetime = time.strptime(recent_ride['start_date_local'], "%Y-%m-%dT%H:%M:%SZ")
        time_start = time.strftime("%B %d, %Y at %I:%M %p", ride_datetime)

        name = recent_ride['name']
        location = ""

        if not recent_ride['location_city'] or not recent_ride['location_state']:
            if not recent_ride['type'] == "VirtualRide":
                try:
                    location = await self.bot.utils.Location.get_location_by_latlon(self.bot, 
                                                                                    recent_ride['start_latlng'][0], 
                                                                                    recent_ride['start_latlng'][1])
                except:
                    location = ""
        else:
            location = f"{recent_ride['location_city']}, {recent_ride['location_state']}"

        if location:
            location = f"near {location} "
        ride_id = recent_ride['id']

        # Try to get the average heart rate
        if 'average_heartrate' in recent_ride:
            avg_hr = recent_ride['average_heartrate']
        else:   # Heart not found
            avg_hr = False 
        
        if athlete and athlete['measurement_preference'] == "feet":
            avg_speed = "{} mph".format(self.meters_per_second_to_miles_per_hour(recent_ride['average_speed']))
            distance = "{} mi".format(self.meters_to_miles(recent_ride['distance']))
            max_speed = "{} mph".format(self.meters_per_second_to_miles_per_hour(recent_ride['max_speed']))
            climbed = "{} feet".format(self.meters_to_feet(recent_ride['total_elevation_gain']))
            # Output string  
        else:
            avg_speed = "{} km/h".format(round(float(recent_ride['average_speed']) * 3.6,1)) #meters per second to km/h
            distance = "{} km".format(round(float(recent_ride['distance']/1000),1)) #meters to km
            max_speed = "{} km/h".format(round(float(recent_ride['max_speed']) * 3.6,1)) #m/s to km/h
            climbed = "{} meters".format(recent_ride['total_elevation_gain'])

        # Figure out if we need to add average watts to the string.
        # Users who don't have a weight won't have average watts.

        out = f"[{name} {location}on {time_start}](<http://www.strava.com/activities/{ride_id}>)\n"
        if recent_ride['type'].lower() == "run":
            avg_pace_mi = self.meters_per_second_to_minutes_per_mile(recent_ride['average_speed'])
            avg_pace_km = self.meters_per_second_to_minutes_per_km(recent_ride['average_speed'])
            out += f"{recent_ride['type']} Stats: {distance} in {moving_time} | Avg pace: {avg_pace_mi} /mi - {avg_pace_km} /km | {climbed} climbed"
            if avg_hr:
                out += f" | Avg HR: {int(avg_hr)} bpm"
        else:
            out += f"{recent_ride['type']} Stats: {distance} in {moving_time} | {avg_speed} average / {max_speed} max | {climbed} climbed"

        if 'suffer_score' in recent_ride:
            out += f" | Effort: {int(recent_ride['suffer_score'])}"

        if 'average_watts' in recent_ride:
            out += f" | {int(recent_ride['average_watts'])} watts average power"
            if avg_hr > 0: 
               out += " | {} watts/bpm".format(round(recent_ride['average_watts']/avg_hr,2))
        
        return out

    async def check_strava_token(self):
        # Unused for now but might be if I impl user tokens
        url = "https://www.strava.com/api/v3/athlete"
        headers = {'Authorization': 'Bearer ' + self.token}
        async with self.bot.session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return False
            else:
                return True

    async def strava_get_athlete_info(self, athlete_id):
        print(f"Getting strava athlete info {athlete_id}")
        url = f"https://www.strava.com/api/v3/athletes/{athlete_id}"
        headers = {'Authorization': 'access_token ' + self.token}
        async with self.bot.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                athlete_info = await resp.json()
                return athlete_info
            else:
                return None

    async def strava_get_ride_extended_info(self, ride_id):
        """ Get all the details about a ride. """
        url = f"https://www.strava.com/api/v3/activities/{ride_id}"
        headers = {'Authorization': 'access_token ' + self.token}
        async with self.bot.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return False

    def meters_per_second_to_minutes_per_mile(self, mps):
        if mps == 0:
            return 0
        secs_per_mile = round(1/(0.000621371 * float(mps)), 1)
        return time.strftime("%M:%S", time.gmtime(secs_per_mile))
    
    def meters_per_second_to_minutes_per_km(self, mps):
        if mps == 0:
            return 0
        secs_per_km = round(1000.0 / mps, 1)
        return time.strftime("%M:%S", time.gmtime(secs_per_km))

    def meters_per_second_to_miles_per_hour(self, mps):
        """ Converts meters per second to miles per hour, who the fuck uses this to measure bike speed? Idiots. """
        mph = 2.23694 * float(mps)
        return round(mph, 1)


    def meters_per_hour_to_miles_per_hour(self, meph):
        """ Convert meters per hour to miles per hour. """
        mph = 0.000621371192 * float(meph)
        return round(mph, 1)


    def meters_to_miles(self, meters):
        """ Convert meters to miles. """
        miles = 0.000621371 * float(meters)
        return round(miles, 1)


    def meters_to_feet(self, meters):
        """ Convert meters to feet. """
        feet = 3.28084 * float(meters)
        return int(round(feet, 1))

async def setup(bot):
    strava = Strava(bot)
    await bot.add_cog(strava)

