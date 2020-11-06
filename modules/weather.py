import asyncio
import discord
from discord.ext import commands
import re
import xml.dom.minidom
from urllib.parse import quote as uriquote
import pytz
from datetime import datetime, timedelta
from utils.time import human_timedelta


WEMOJI ={
    "cloudy": "\N{CLOUD}",
    "partly-cloudy-day": "\N{WHITE SUN WITH SMALL CLOUD}",
    "partly-cloudy-night": "\N{CLOUD}\N{CRESCENT MOON}",
    "clear-day": "\N{BLACK SUN WITH RAYS}",
    "clear-night": "\N{CRESCENT MOON}",
    "rain": "\N{CLOUD WITH RAIN}",
    "snow": "\N{SNOWFLAKE}",
    "sleet": "\N{SNOWFLAKE}\N{CLOUD WITH RAIN}",
    "wind": "\N{DASH SYMBOL}",
    "fog": "\N{FOG}"
} 


class Weather(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def locatamatron(self, ctx, location = ""):
        if not location:
            loc = ctx.author_info.location
            if loc:
                return loc
            else:
                await ctx.send("I don't have a location for you - use `set location <location>` to set one")
        else:
            return await self.bot.utils.Location.from_google_geocode(self.bot, location)


    @commands.command(name='w', aliases=['pw'])
    async def forecast_io(self, ctx, *, location:str = ""):
        """Show a weather report from forecast.io for <location>
           Can be invoked without location if you have done a `set location`"""
        key = self.bot.config.forecast_io_key
        loc = await self.locatamatron(ctx, location)
        if not loc:
            return

        url = f"https://api.forecast.io/forecast/{key}/{loc.latitude},{loc.longitude}"
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            weather = await self.parse_fio(data)
            if ctx.invoked_with.lower() == "w":
                await ctx.send(await self.fio_text(weather, loc))
            else:
                await ctx.send(embed=await self.fio_embed(weather, loc))


    async def fio_text(self, data, loc):
        if data['feels_like_f'] == data['temp_f']:
            data['feels_like_f'] = ''
            data['feels_like_c'] = ''
        else:
            data['feels_like_f'] = f" / Feels Like: {data['feels_like_f']}"
            data['feels_like_c'] = f" / Feels Like: {data['feels_like_c']}"
        data['icon'] = WEMOJI.get(data['icon'], '')

        out = f"{loc.formatted_address} / "
        if loc.country == "United States":
            out += ("{condition} {icon} / {temp_f} ({temp_c}){feels_like_f} / "
                    "Humidity: {humidity} / Wind: {wind_direction} at {wind_speed_mi} / "
                    "Cloud Cover: {cloud_cover} / High: {high_f} Low: {low_f} / "
                    "Outlook: {outlook_imperial}").format(**data)
        else:
            out += ("{condition} {icon} / {temp_c} ({temp_f}){feels_like_c} / Dewpoint: {dewpoint_c} / "
                    "Humidity: {humidity} / Wind: {wind_direction} at {wind_speed_km} / "
                    "Cloud Cover: {cloud_cover} / High: {high_c} Low: {low_c} / "
                    "Outlook: {outlook_metric}").format(**data)

        return out

    async def fio_embed(self, data, loc):
        e = discord.Embed(title=f"{loc.formatted_address} - {data['condition']}")
        e.set_footer(text=self.bot.utils.units.imperial_string_to_metric(data['outlook_imperial'], both=True))
        wicons = "https://raw.githubusercontent.com/iamsix/palbot/rewrite/utils/wicons/{}.png"
        e.set_thumbnail(url=wicons.format(data['icon'].lower()))
        e.add_field(name="Temp", value=f"{data['temp_c']} / {data['temp_f']}")
        if data['feels_like_f'] != data['temp_f']:
            e.add_field(name="Feels Like", value=f"{data['feels_like_c']} / {data['feels_like_f']}")
        e.add_field(name="Humidity", value=data['humidity'])
        e.add_field(name="High", value=f"{data['high_c']} / {data['high_f']}")
        e.add_field(name="Low", value=f"{data['low_c']} / {data['low_f']}")
        e.add_field(name="Wind", value="{wind_direction} at {wind_speed_km} / {wind_speed_mi}".format(**data))
        return e

    

    async def parse_fio(self, data):
        units = self.bot.utils.units
        current = data['currently']

        wind_direction = current['windBearing']
        wind_arrow = units.bearing_to_arrow(wind_direction)
        wind_direction = f"{wind_arrow} {units.bearing_to_compass(wind_direction)}"
        wind_speed_km = f"{units.mi_to_km(current['windSpeed'])} km/h"
        wind_speed_mi = f"{int(round(current['windSpeed'], 0))} mph"
        
        try:
            outlook_imp = f"{data['minutely']['summary']} {data['daily']['summary']}"
        except:
            outlook_imp = f"{data['hourly'].get('summary', '')} {data['daily'].get('summary', '')}"
        outlook_metric = units.imperial_string_to_metric(outlook_imp)

        temp_c = f"{units.f_to_c(current['temperature'])}°C"
        temp_f = f"{int(round(current['temperature'],0))}°F"
        feels_like_c = f"{units.f_to_c(current['apparentTemperature'])}°C"
        feels_like_f = f"{int(round(current['apparentTemperature'],0))}°F"

        low_c = f"{units.f_to_c(data['daily']['data'][0]['temperatureMin'])}°C"
        low_f = f"{int(round(data['daily']['data'][0]['temperatureMin'],0))}°F"
        high_c = f"{units.f_to_c(data['daily']['data'][0]['temperatureMax'])}°C"
        high_f = f"{int(round(data['daily']['data'][0]['temperatureMax'],0))}°F"

        dewpoint_c = f"{units.f_to_c(current['dewPoint'])}°C"
        dewpoint_f = f"{int(round(current['dewPoint'],0))}°F"
        
        weather = {'condition': current['summary'],
                   'icon': current['icon'],
                   'humidity' : f"{int(100*current['humidity'])}%",
                   'cloud_cover' : f"{int(100*current['cloudCover'])}%",
                   'wind_direction': wind_direction,
                   'wind_speed_km' : wind_speed_km,
                   'wind_speed_mi' : wind_speed_mi,
                   'outlook_imperial': outlook_imp,
                   'outlook_metric' : outlook_metric,
                   'temp_c' : temp_c,
                   'temp_f' : temp_f,
                   'feels_like_c' : feels_like_c,
                   'feels_like_f' : feels_like_f,
                   'low_c' : low_c,
                   'low_f' : low_f,
                   'high_c' : high_c,
                   'high_f' : high_f,
                   'dewpoint_c' : dewpoint_c,
                   'dewpoint_f' : dewpoint_f,
                   }
        return weather

    @commands.command(name='aqi')
    async def get_aqi(self, ctx, *, location: str = ''):
        """Show the air quality index of <location>
           Can be invoked without location if you have a set location"""
        loc = await self.locatamatron(ctx, location)
        if not loc:
            return

        url = "http://api.waqi.info/feed/{}/?token={}"
        url = url.format(f'geo:{loc.latitude};{loc.longitude}', self.bot.config.aqicn)

        async with self.bot.session.get(url) as resp:
            data = await resp.json()

        if data['status'] != "ok":
            return

        data = data['data']
        
        pm25 = data['iaqi']['pm25']['v']

        conditions = {
            50 :  " (Good)",
            100 : " (Moderate)",
            150 : " (Unhealthy for sensitive groups)",
            200 : " (Unhealthy)",
            300 : " (Very Unhealthy)",
            9999 : " (Hazardous)",
        }
        condition = ""
        for k in conditions:
            if pm25 <= k:
                condition = conditions[k]
                break

        city = data['city']['name']
        out = "{} - Air Quality: PM2.5: {}{}".format(city, pm25, condition)

        try:
            o3 = pm25 = data['iaqi']['o3']['v']
            out += " - Ozone: {}".format(o3)
        except:
            pass
        
        await ctx.send(out)

    @commands.command()
    async def metar(self, ctx, station: str):
        """Get the Metar aviation weather report for an airport <station>"""
        url = ('http://aviationweather.gov/adds/dataserver_current/httpparam?'
               'dataSource=metars&requestType=retrieve&format=xml&' 
              f'stationString={station}&hoursBeforeNow=2&mostRecent=true')
        async with self.bot.session.get(url) as resp:
            data = await resp.read()
            dom = xml.dom.minidom.parseString(data)
            text = dom.getElementsByTagName('raw_text')
            if text:
                await ctx.send(text[0].childNodes[0].data)
            else:
                await ctx.send(f"Failed to find METAR for `{station}` - it needs an airpot ICAO code such as KJFK")
    @metar.error
    async def metar_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("No station provided, try an ICAO code such as `metar KJFK`")



    @commands.command(name='wu')
    async def wunderground(self, ctx, *, location: str = None):
        """Show a weather report from weather underground for <location>
           Can be invoked without location if you have done a `set location`"""
        key = self.bot.config.wunderground_key
        loc = await self.locatamatron(ctx, location)
        if not loc:
            return
        
        url = f"http://api.wunderground.com/api/{key}/conditions/q/{uriquote(loc.user_input_location)}.json"
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            data = data['current_observation']

        city = data['display_location']['full']
        temp_f = data['temp_f']
        temp_c = data['temp_c']
        condition = data['weather']
        icon = WEMOJI.get(data['icon'], '')
        humidity = "Humidity: {}".format(data['relative_humidity'])
        wind = "Wind: {}".format(data['wind_string'])
        wind = self.bot.utils.units.imperial_string_to_metric(wind, both=True)

        out = f"{city} / {condition} {icon} / {temp_c}°C {temp_f}°F / {humidity} / {wind}"        
        await ctx.send(out)
    

    @commands.command()
    async def sun(self, ctx, *, location: str = None):
        """Show sunrise/sunset for a <location>
           Can be invoked without location if you have done a `set location`"""
        key = self.bot.config.forecast_io_key
        loc = await self.locatamatron(ctx, location)
        if not loc:
            return
            
        url = "https://api.forecast.io/forecast/{}/{},{}"
        url = url.format(key, loc.latitude, loc.longitude)

        async with self.bot.session.get(url) as resp:
            data = await resp.json()

        tmz = pytz.timezone(data['timezone'])
        now = datetime.fromtimestamp(int(data['currently']['time']), tz=tmz)
        data = data['daily']['data'][0]

        sunriseobj = datetime.fromtimestamp(int(data['sunriseTime']), tz=tmz)
        sunsetobj = datetime.fromtimestamp(int(data['sunsetTime']), tz=tmz)
        sunlength = sunsetobj - sunriseobj

        til = human_timedelta(sunriseobj, source=now, suffix=True)
        sunrise = sunriseobj.strftime("%H:%M")
        sunrise = f"{sunrise} ({til})"

        til = human_timedelta(sunsetobj, source=now, suffix=True)
        sunset = sunsetobj.strftime("%H:%M")
        sunset = f"{sunset} ({til})"

        out = f"{loc.formatted_address} / Sunrise: {sunrise} / Sunset: {sunset} / Day Length: {sunlength}"
        await ctx.send(out)


def setup(bot):
    bot.add_cog(Weather(bot))

