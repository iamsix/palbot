import discord
from discord.ext import commands

import datetime
import time
from urllib.parse import quote as uriquote
#from bs4 import BeautifulSoup

class Strava(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="strava", case_insensitive=True, invoke_without_command=True)
    async def _strava(self, ctx, user: int = 0):
        """Show your most recent ride from strava.com
           Optionally provide a [user] ID to show the most recent ride of
           use `set strava <id>` to set your strava ID"""

        user = user or ctx.author_info.strava
        self.token = token = self.bot.config.stravaToken

        output = ""
        if user:
            if await self.strava_is_valid_user(user):
                # Process a last ride request for a specific strava id.
                url = f"https://www.strava.com/api/v3/athletes/{user}/activities"
                headers = {'Authorization': 'access_token ' + token}
                async with self.bot.session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        output = f"Unable to retrieve rides from Strava ID: {user}"
                    else:
                        data = await resp.json()
                        output = await self.strava_extract_latest_ride(data, user)
            else:
                output = f"Sorry, `{user}` doesn't seem to be a valid Strava user."
            
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
    

    async def check_strava_token(self, token):
        url = "https://www.strava.com/api/v3/athlete"
        headers = {'Authorization': 'Bearer ' + token}
        async with self.bot.session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return False
            else:
                return True

    async def strava_extract_latest_ride(self, data, user):
        """ Grab the latest ride from a list of rides and gather some statistics about it """
        if data:
            recent_ride = data[0]
            recent_ride = await self.strava_get_ride_extended_info(recent_ride['id'])
            if recent_ride:
                measurements = await self.strava_get_measurement_pref(user)
                return self.parse_strava_ride(recent_ride, user, measurements)
            else:
                return f"Sorry {user}, an error has occured attempting to retrieve the most recent ride's details"
        else:
            return f"Sorry {user}, no rides have been recorded yet. Remember, if it's not on Strava, it didn't happen."


    def parse_strava_ride(self, recent_ride, athlete_id=None, measurement_pref=None):
        #if the athlete ID is missing we can default to mph
        moving_time = str(datetime.timedelta(seconds=recent_ride['moving_time']))
        ride_datetime = time.strptime(recent_ride['start_date_local'], "%Y-%m-%dT%H:%M:%SZ")
        time_start = time.strftime("%B %d, %Y at %I:%M %p", ride_datetime)

        name = recent_ride['name']
        location = f"{recent_ride['location_city']}, {recent_ride['location_state']}"
        ride_id = recent_ride['id']

        # Try to get the average heart rate
        if 'average_heartrate' in recent_ride:
            avg_hr = recent_ride['average_heartrate']
        else:   # Heart not found
            avg_hr = False 
        
        if measurement_pref == "feet" or athlete_id == None or measurement_pref == None:
            avg_speed = "{} mph".format(self.meters_per_second_to_miles_per_hour(recent_ride['average_speed']))
            distance = "{} mi".format(self.meters_to_miles(recent_ride['distance']))
            max_speed = "{} mph".format(self.meters_per_second_to_miles_per_hour(recent_ride['max_speed']))
            climbed = "{} feet".format(self.meters_to_feet(recent_ride['total_elevation_gain']))
            # Output string  
        elif measurement_pref == "meters":
            avg_speed = "{} km/h".format(round(float(recent_ride['average_speed']) * 3.6,1)) #meters per second to km/h
            distance = "{} km".format(round(float(recent_ride['distance']/1000),1)) #meters to km
            max_speed = "{} km/h".format(round(float(recent_ride['max_speed']) * 3.6,1)) #m/s to km/h
            climbed = "{} meters".format(recent_ride['total_elevation_gain'])

        # Figure out if we need to add average watts to the string.
        # Users who don't have a weight won't have average watts.
        
        
        out = f"{name} near {location} on {time_start} [ <http://www.strava.com/activities/{ride_id}> ]\n"
        out += f"Ride Stats: {distance} in {moving_time} | {avg_speed} average / {max_speed} max | {climbed} climbed"

        if 'average_watts' in recent_ride:
            out += f" | {int(recent_ride['average_watts'])} watts average power"
            if avg_hr > 0: 
               out += " | {} watts/bpm".format(round(recent_ride['average_watts']/avg_hr,2))
        
        return out



    async def strava_get_measurement_pref(self, athlete_id):
        url = f"https://www.strava.com/api/v3/athletes/{athlete_id}"
        headers = {'Authorization': 'access_token ' + self.token}
        async with self.bot.session.get(url, headers=headers) as resp:
            if resp.status == 200:
                athlete_info = await resp.json()
                return athlete_info['measurement_preference']
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

    async def strava_is_valid_user(self, strava_id):
        """ Checks to see if a strava id is a valid strava user """
        url = f"http://app.strava.com/athletes/{strava_id}"
        async with self.bot.session.get(url) as resp:
            if resp.status == 200:
                return True
            else:
                return False

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
        return round(feet, 1)

def setup(bot):
    bot.add_cog(Strava(bot))
