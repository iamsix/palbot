import asyncio
import discord
from discord.ext import commands
import re
import xml.dom.minidom
from urllib.parse import quote as uriquote
import pytz
from datetime import datetime, timedelta
from utils.time import human_timedelta

#TODO: yr.no
# https://api.met.no/weatherapi/locationforecast/2.0/complete?lat=-16.516667&lon=-68.166667&altitude=4150
# altitude is optional
# https://api.met.no/weatherapi/locationforecast/2.0/documentation

WEMOJI ={
    "cloudy": "\N{CLOUD}",
    "partly-cloudy-day": "\N{WHITE SUN WITH SMALL CLOUD}",
    "partly-cloudy-night": "\N{CLOUD}\N{CRESCENT MOON}",
    "clear-day": "\N{BLACK SUN WITH RAYS}\N{VARIATION SELECTOR-16}",
    "clear-night": "\N{CRESCENT MOON}",
    "rain": "\N{CLOUD WITH RAIN}",
    "snow": "\N{SNOWFLAKE}",
    "sleet": "\N{SNOWFLAKE}\N{CLOUD WITH RAIN}",
    "wind": "\N{DASH SYMBOL}",
    "fog": "\N{FOG}",
        1 : "\N{BLACK SUN WITH RAYS}\N{VARIATION SELECTOR-16}",
        2 : "\N{WHITE SUN WITH SMALL CLOUD}",
        3 : "\N{WHITE SUN BEHIND CLOUD}",
        4 : "\N{WHITE SUN WITH SMALL CLOUD}",
        5 : "\N{BLACK SUN WITH RAYS}\N{VARIATION SELECTOR-16}\N{FOG}",
        6 : "\N{WHITE SUN BEHIND CLOUD}",
        7 : "\N{CLOUD}\N{VARIATION SELECTOR-16}",
        8 : "\N{CLOUD}\N{VARIATION SELECTOR-16}",
        11: "\N{FOG}",
        12: "\N{CLOUD WITH RAIN}",
        13: "\N{WHITE SUN BEHIND CLOUD WITH RAIN}",
        14: "\N{WHITE SUN BEHIND CLOUD WITH RAIN}",
        15: "\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",
        16: "\N{WHITE SUN BEHIND CLOUD}\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",
        17: "\N{WHITE SUN BEHIND CLOUD}\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",
        18: "\N{CLOUD WITH RAIN}",
        19: "\N{DASH SYMBOL}\N{SNOWFLAKE}",
        20: "\N{DASH SYMBOL}\N{SNOWFLAKE}\N{WHITE SUN BEHIND CLOUD}",
        21: "\N{DASH SYMBOL}\N{SNOWFLAKE}\N{WHITE SUN BEHIND CLOUD}",
        22: "\N{SNOWFLAKE}",
        23: "\N{SNOWFLAKE}\N{WHITE SUN BEHIND CLOUD}",
        24: "\N{ICE CUBE}",
        25: "\N{SNOWFLAKE}\N{CLOUD WITH RAIN}",
        26: "\N{ICE CUBE}\N{CLOUD WITH RAIN}",
        29: "\N{SNOWFLAKE}\N{CLOUD WITH RAIN}",
        30: "\N{OVERHEATED FACE}",
        31: "\N{FREEZING FACE}",
        31: "\N{FREEZING FACE}",
        32: "\N{DASH SYMBOL}",
        33: "\N{CRESCENT MOON}",
        34: "\N{CRESCENT MOON}\N{CLOUD}",
        35: "\N{CRESCENT MOON}\N{CLOUD}",
        36: "\N{CRESCENT MOON}\N{CLOUD}",
        37: "\N{CRESCENT MOON}\N{FOG}",
        38: "\N{CRESCENT MOON}\N{CLOUD}",
        39: "\N{CRESCENT MOON}\N{CLOUD WITH RAIN}",
        40: "\N{CRESCENT MOON}\N{CLOUD WITH RAIN}",
        41: "\N{CRESCENT MOON}\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",
        42: "\N{CRESCENT MOON}\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",
        43: "\N{CRESCENT MOON}\N{DASH SYMBOL}\N{SNOWFLAKE}",
        44: "\N{CRESCENT MOON}\N{SNOWFLAKE}",
        "wc0": "\N{CLOUD WITH TORNADO}",
        "wc1": "\N{CYCLONE}",
        "wc2": "\N{CYCLONE}",
        "wc3": "\N{THUNDER CLOUD AND RAIN}",
        "wc4": "\N{THUNDER CLOUD AND RAIN}",
        "wc5": "\N{SNOWFLAKE}\N{CLOUD WITH RAIN}",
        "wc6": "\N{SNOWFLAKE}\N{CLOUD WITH RAIN}",
        "wc7": "\N{SNOWFLAKE}\N{CLOUD WITH RAIN}",
        "wc8": "\N{ICE CUBE}\N{CLOUD WITH RAIN}",
        "wc9": "\N{CLOUD WITH RAIN}",
        "wc10": "\N{ICE CUBE}\N{CLOUD WITH RAIN}",
        "wc11": "\N{CLOUD WITH RAIN}",
        "wc12": "\N{CLOUD WITH RAIN}",
        "wc13": "\N{SNOWFLAKE}",
        "wc14": "\N{SNOWFLAKE}",
        "wc15": "\N{DASH SYMBOL}\N{SNOWFLAKE}",
        "wc16": "\N{SNOWFLAKE}",
        "wc17": "\N{SNOWFLAKE}",
        "wc18": "\N{SNOWFLAKE}\N{CLOUD WITH RAIN}",
        "wc19": "\N{FOG}",
        "wc20": "\N{FOG}",
        "wc21": "\N{FOG}",
        "wc22": "\N{FOG}",
        "wc23": "\N{DASH SYMBOL}",
        "wc24": "\N{DASH SYMBOL}",
        "wc25": "\N{ICE CUBE}\N{DASH SYMBOL}",
        "wc26": "\N{CLOUD}",
        "wc27": "\N{CLOUD}",
        "wc28": "\N{WHITE SUN BEHIND CLOUD}",
        "wc29": "\N{CRESCENT MOON}\N{CLOUD}",
        "wc30": "\N{WHITE SUN WITH SMALL CLOUD}",
        "wc31": "\N{CRESCENT MOON}",
        "wc32": "\N{BLACK SUN WITH RAYS}\N{VARIATION SELECTOR-16}",
        "wc33": "\N{CRESCENT MOON}",
        "wc34": "\N{WHITE SUN WITH SMALL CLOUD}",
        "wc35": "\N{ICE CUBE}\N{CLOUD WITH RAIN}",
        "wc36": "\N{OVERHEATED FACE}",
        "wc38": "\N{THUNDER CLOUD AND RAIN}",
        "wc40": "\N{CLOUD WITH RAIN}",
        "wc42": "\N{SNOWFLAKE}",
        "wc47": "\N{THUNDER CLOUD AND RAIN}",
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
                await ctx.send("I don't have a location for you - use `!set location <location>` to set one")
        else:
            return await self.bot.utils.Location.from_google_geocode(self.bot, location)

    @commands.command()
    async def wq(self, ctx, *, location:str = ""):
        ctx.invoked_with = "w"
        await self.forecast_io(ctx, location=location)
        await self.get_aqi(ctx, location=location)

    @commands.command(name='piw', aliases=['ppiw'])
    async def forecast_io(self, ctx, *, location:str = ""):
        """Show a weather report from forecast.io for <location>
           Can be invoked without location if you have done a `set location`"""
        key = self.bot.config.forecast_io_key
        loc = await self.locatamatron(ctx, location)
        if not loc:
            return
        url = f"https://api.pirateweather.net/forecast/{key}/{loc.latitude},{loc.longitude}"
#        url = f"https://api.forecast.io/forecast/{key}/{loc.latitude},{loc.longitude}"
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
            data['feels_like_f'] = f" / RealFeelz™: {data['feels_like_f']}"
            data['feels_like_c'] = f" / RealFeelz™: {data['feels_like_c']}"

        
        data['icon'] = WEMOJI.get(data['icon'], '')


        out = f"{loc.formatted_address} / "
        if loc.country == "United States":
            out += ("{condition} {icon} / {temp_f} ({temp_c}){feels_like_f} / Dewpoint: {dewpoint_f} / "
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
        wicon = f"https://raw.githubusercontent.com/iamsix/palbot/master/utils/wicons/{data['icon']}.png".lower()
        e.set_thumbnail(url=wicon)
        e.add_field(name="Temp", value=f"{data['temp_c']} / {data['temp_f']}")
        if data['feels_like_f'] != data['temp_f']:
            e.add_field(name="RealFeelz™", value=f"{data['feels_like_c']} / {data['feels_like_f']}")
        e.add_field(name="Humidity", value=data['humidity'])
        e.add_field(name="High", value=f"{data['high_c']} / {data['high_f']}")
        e.add_field(name="Low", value=f"{data['low_c']} / {data['low_f']}")
        e.add_field(name=f"Wind {data['wind_direction']}", value="{wind_speed_km}\n{wind_speed_mi}".format(**data))
        return e

    

    async def parse_fio(self, data):
        units = self.bot.utils.units
        current = data['currently']

        wind_direction = current['windBearing']
        wind_arrow = units.bearing_to_arrow(wind_direction)
        wind_direction = f"{wind_arrow} {units.bearing_to_compass(wind_direction)}"
        wind_speed_km = f"{units.mi_to_km(current['windSpeed'])} km/h"
        wind_speed_mi = f"{int(round(current['windSpeed'], 0))} mph"
        if current['windGust'] - 5 >  current['windSpeed']:
            wind_speed_km += f" gusting to {units.mi_to_km(current['windGust'])} km/h"
            wind_speed_mi += f" gusting to {int(round(current['windGust'], 0))} mph"

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


    @commands.command(name='w', aliases=['pw'])
    async def accuweather(self, ctx, *, location:str = ""):
        """Show a weather report from accuweather for <location>
           Can be invoked without location if you have done a `set location`"""
        key = self.bot.config.accuweather_key
        loc = await self.locatamatron(ctx, location)
        if not loc:
            await ctx.send(f"Location not found: `{location}`")
            return
        
        latlong = f'{loc.latitude},{loc.longitude}'
        locurl = f"http://api.accuweather.com/locations/v1/search?q={latlong}&apikey={key}"
        async with self.bot.session.get(locurl) as resp:
            data = await resp.json()
            accu_loc = data[0]['Key']

        url = f'http://api.accuweather.com/localweather/v1/{accu_loc}.json?apikey={key}&details=true'
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            weather = self.parse_accu(data)
            if ctx.invoked_with.lower() == "w":
                await ctx.send(await self.fio_text(weather, loc))
            else:
                await ctx.send(embed=await self.fio_embed(weather, loc))
    
    def parse_accu(self, data):
        units = self.bot.utils.units
        current = data['CurrentConditions']
        forecast = data['ForecastSummary']['DailyForecasts']
    
        wind_direction = current['Wind']['Direction']['Degrees']
        wind_arrow = units.bearing_to_arrow(wind_direction)
        wind_direction = f"{wind_arrow} {units.bearing_to_compass(wind_direction)}"

        windspeed = current['Wind']['Speed']['Value']
        gustspeed = current['WindGust']['Speed']['Value']

        wind_speed_km = f"{units.mi_to_km(windspeed)} km/h"
        wind_speed_mi = f"{int(round(windspeed, 0))} mph"
        if gustspeed - 5 > windspeed:
            wind_speed_km += f" gusting to {units.mi_to_km(gustspeed)} km/h"
            wind_speed_mi += f" gusting to {int(round(gustspeed, 0))} mph"

        summary = f"{forecast[0]['Day']['LongPhrase']} in the day, "
        summary += f"{forecast[0]['Night']['LongPhrase']} at night."
        outlook_imp = f"{summary} {data['ForecastSummary']['Headline']['Text']}"

        # extended stuff if necessary
        uv = f"UV Index: {current['UVIndex']} ({current['UVIndexText']}) " if current['UVIndex'] > 0 else ""
        pollen = ""
        for pol in forecast[0]['AirAndPollen']:
            if pol['Name'] == "Tree" and  pol['Value'] > 0:
                pollen = f"Tree Pollen: {pol['Value']} ({pol['Category']})"

        if uv or pollen:
             outlook_imp += f"\n{uv}{pollen}"
        # end of jank
        outlook_metric = units.imperial_string_to_metric(outlook_imp)

        temp_c = f"{units.f_to_c(current['Temperature']['Value'])}°C"
        temp_f = f"{int(round(current['Temperature']['Value'],0))}°F"
        feels_like_c = f"{units.f_to_c(current['RealFeelTemperature']['Value'])}°C"
        feels_like_f = f"{int(round(current['RealFeelTemperature']['Value'],0))}°F"

        low_c = f"{units.f_to_c(forecast[0]['Temperature']['Minimum']['Value'])}°C"
        low_f = f"{int(round(forecast[0]['Temperature']['Minimum']['Value'],0))}°F"
        high_c = f"{units.f_to_c(forecast[0]['Temperature']['Maximum']['Value'])}°C"
        high_f = f"{int(round(forecast[0]['Temperature']['Maximum']['Value'],0))}°F"
        
        dewpoint_c = f"{units.f_to_c(current['DewPoint']['Value'])}°C"
        dewpoint_f = f"{int(round(current['DewPoint']['Value'],0))}°F"
 
        weather = {
                'condition' : current['WeatherText'],
                'icon' : current['WeatherIcon'],
                'humidity' : f"{current['RelativeHumidity']}%",
                'cloud_cover' : f"{current['CloudCover']}%",
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


    @commands.command(name="yr", aliases=['pyr'])
    async def yr(self, ctx, * ,location:str = ""):
        """Show a weather report from yr.no for <location>
        Can be invoked without location if you have done a `set location`"""
        loc = await self.locatamatron(ctx, location)
        if not loc:
            return

        url="https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={}&lon={}"
        url = url.format(loc.latitude, loc.longitude)
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            now = data['properties']['timeseries'][0]['data']

        weather = self.parse_yr(now)

        if ctx.invoked_with.lower() == "yr":
            await ctx.send(await self.fio_text(weather, loc))
        else:
            await ctx.send(embed=await self.fio_embed(weather, loc))


    def parse_yr(self, data):
        units = self.bot.utils.units
        now = data['instant']['details']

        temp_c = f"{int(round(now['air_temperature'],0))}°C"
        temp_f = f"{units.c_to_f(now['air_temperature'])}°F"

        wind_direction = now['wind_from_direction']
        wind_arrow = units.bearing_to_arrow(wind_direction)
        wind_direction = f"{wind_arrow} {units.bearing_to_compass(wind_direction)}"

        wind_speed = int(round(now['wind_speed'] * 3.6, 0))
        wind_speed_km = f"{wind_speed} km/h"
        wind_speed_mi = f"{units.km_to_mi(wind_speed)} mph"

        dewpoint_c = f"{now['dew_point_temperature']}°C"
        dewpoint_f = f"{units.c_to_f(now['dew_point_temperature'])}°F"

        low = data['next_6_hours']['details']['air_temperature_min']
        high = data['next_6_hours']['details']['air_temperature_max']
        low_c = f"{int(round(low, 0))}°C"
        low_f = f"{units.c_to_f(low)}°F"
        high_c = f"{int(round(high, 0))}°C"
        high_f = f"{units.c_to_f(high)}°F"

        fc = data['next_12_hours']['summary']['symbol_code']

        condition = data['next_6_hours']['summary']['symbol_code']
        precip = data['next_6_hours']['details']['precipitation_amount']
        outlook = f"{condition} with precipitation {precip}mm in next 6 hours. Next 12hr is {fc}"

        weather = {
                'condition' : data['next_1_hours']['summary']['symbol_code'],
                'icon': "", #TODO : wicons with day/night based on condition
                'humidity': f"{int(now['relative_humidity'])}%",
                'wind_direction': wind_direction,
                'wind_speed_km': wind_speed_km,
                'wind_speed_mi': wind_speed_mi,
                'cloud_cover':  f"{int(now['cloud_area_fraction'])}%",
                'outlook_imperial': outlook,
                'outlook_metric': outlook,
                'temp_c': temp_c,
                'temp_f': temp_f,
                'feels_like_c': temp_c,
                'feels_like_f': temp_f,
                'low_c': low_c,
                'low_f': low_f,
                'high_c': high_c,
                'high_f': high_f,
                'dewpoint_c': dewpoint_c,
                'dewpoint_f': dewpoint_f,
                }
        return weather



    @commands.command(name='wc', aliases=['pwc'])
    async def weathercom(self, ctx, *, location:str = ""):
        """Show a weather report from weather.com for <location>
           Can be invoked without location if you have done a `set location`"""
        key = self.bot.config.weathercom_key
        loc = await self.locatamatron(ctx, location)
        if not loc:
            return


       
        fcurl= f'https://api.weather.com/v1/geocode/{loc.latitude}/{loc.longitude}/forecast/daily/3day.json?apiKey={key}&units=e'
        async with self.bot.session.get(fcurl) as resp:
            data = await resp.json()
            forecast = data['forecasts']

        url = f"https://api.weather.com/v3/wx/observations/current"
        params = {"geocode": f'{loc.latitude},{loc.longitude}',
                "units" : "e", "format" : "json", "language": "en-US",
                  "apiKey": key,
                  }
        async with self.bot.session.get(url, params=params) as resp:
            data = await resp.json()
            weather = self.parse_wc(data, forecast)
            if ctx.invoked_with.lower() == "wc":
                await ctx.send(await self.fio_text(weather, loc))
            else:
                await ctx.send(embed=await self.fio_embed(weather, loc))
    
    def parse_wc(self, current, forecast):
        units = self.bot.utils.units
  
        wind_direction = current['windDirection']
        wind_arrow = units.bearing_to_arrow(wind_direction)
        wind_direction = f"{wind_arrow} {units.bearing_to_compass(wind_direction)}"

        windspeed = current['windSpeed']
        gustspeed = current['windGust']

        wind_speed_km = f"{units.mi_to_km(windspeed)} km/h"
        wind_speed_mi = f"{int(round(windspeed, 0))} mph"
        if gustspeed and (gustspeed - 5 > windspeed):
            wind_speed_km += f" gusting to {units.mi_to_km(gustspeed)} km/h"
            wind_speed_mi += f" gusting to {int(round(gustspeed, 0))} mph"


        temp_c = f"{units.f_to_c(current['temperature'])}°C"
        temp_f = f"{int(round(current['temperature'],0))}°F"
        feels_like_c = f"{units.f_to_c(current['temperatureFeelsLike'])}°C"
        feels_like_f = f"{int(round(current['temperatureFeelsLike'],0))}°F"

        dewpoint_c = f"{units.f_to_c(current['temperatureDewPoint'])}°C"
        dewpoint_f = f"{int(round(current['temperatureDewPoint'],0))}°F"

        if 'day' in forecast[0]:
            curfc = forecast[0]['day']
        else:
            curfc = forecast[0]['night']
        low_c = f"{units.f_to_c(forecast[0]['min_temp'])}°C"
        low_f = f"{int(round(forecast[0]['min_temp'],0))}°F"
        high_c = f"{units.f_to_c(curfc['hi'])}°C"
        high_f = f"{int(round(curfc['hi'],0))}°F"
        cloudcover = f"{curfc['clds']}%"

        outlook_imp = f"Today: {forecast[0]['narrative']} Tomorrow: {forecast[1]['narrative']}"
        outlook_metric = units.imperial_string_to_metric(outlook_imp)
        
        weather = {
                'condition' : current['wxPhraseLong'],
                'icon' : f"wc{current['iconCode']}",
                'humidity' : f"{current['relativeHumidity']}%",
                'wind_direction': wind_direction,
                'wind_speed_km' : wind_speed_km,
                'wind_speed_mi' : wind_speed_mi,
                'cloud_cover' : cloudcover,
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


    @commands.command(name='vc', aliases=['pvc'])
    async def visual_crossing(self, ctx, *, location:str = ""):
        """Show a weather report from Visual Crossing for <location>
           Can be invoked without location if you have done a `set location`"""
        key = self.bot.config.vcrossing_key
        loc = await self.locatamatron(ctx, location)
        if not loc:
            return

        url = f'https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/'
        url += f'{loc.latitude},{loc.longitude}?key={key}'
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            weather = await self.parse_vc(data)
            if ctx.invoked_with.lower() == "vc":
                await ctx.send(await self.fio_text(weather, loc))
            else:
                await ctx.send(embed=await self.fio_embed(weather, loc))

    async def parse_vc(self, data):
        units = self.bot.utils.units
        current = data['currentConditions']
        forecast = data['days'][0]
        summary = forecast['description'] + " " + data['description'] 

        wind_direction = current['winddir']
        wind_arrow = units.bearing_to_arrow(wind_direction)
        wind_direction = f"{wind_arrow} {units.bearing_to_compass(wind_direction)}"

        windspeed = current['windspeed']
        gustspeed = current['windgust']

        wind_speed_km = f"{units.mi_to_km(windspeed)} km/h"
        wind_speed_mi = f"{int(round(windspeed, 0))} mph"
        if gustspeed and (gustspeed - 5 > windspeed):
            wind_speed_km += f" gusting to {units.mi_to_km(gustspeed)} km/h"
            wind_speed_mi += f" gusting to {int(round(gustspeed, 0))} mph"


        temp_c = f"{units.f_to_c(current['temp'])}°C"
        temp_f = f"{int(round(current['temp'],0))}°F"
        feels_like_c = f"{units.f_to_c(current['feelslike'])}°C"
        feels_like_f = f"{int(round(current['feelslike'],0))}°F"

        dewpoint_c = f"{units.f_to_c(current['dew'])}°C"
        dewpoint_f = f"{int(round(current['dew'],0))}°F"

        low_c = f"{units.f_to_c(forecast['tempmin'])}°C"
        low_f = f"{int(round(forecast['tempmin'],0))}°F"
        high_c = f"{units.f_to_c(forecast['tempmax'])}°C"
        high_f = f"{int(round(forecast['tempmax'],0))}°F"

        weather = {
                'condition' : current['conditions'],
                'icon' : current['icon'],
                'humidity' : f"{current['humidity']}%",
                'wind_direction': wind_direction,
                'wind_speed_km' : wind_speed_km,
                'wind_speed_mi' : wind_speed_mi,
                'cloud_cover' : f"{current['cloudcover']}%",
                'outlook_imperial': summary,
                'outlook_metric' : summary,
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
        
        try:
            pm25 = data['iaqi']['pm25']['v']
        except:
            pm25 = data['aqi']

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
        url = f"https://aviationweather.gov/api/data/metar?ids={station}"
        async with self.bot.session.get(url) as resp:
            data = await resp.read()
            data = data.decode()
            if data:
                await ctx.send(data)
            else:
                await ctx.send(f"Failed to find METAR for `{station}` - it needs an airpot ICAO code such as KJFK")
    @metar.error
    async def metar_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("No station provided, try an ICAO code such as `metar KJFK`")



    # TODO change this to twc or accuweather
    @commands.command(aliases=['sunrise, sunset'])
    async def sun(self, ctx, *, location: str = None):
        """Show sunrise/sunset for a <location>
           Can be invoked without location if you have done a `set location`"""
        key = self.bot.config.forecast_io_key
        loc = await self.locatamatron(ctx, location)
        if not loc:
            return
            
        url = f"https://api.pirateweather.net/forecast/{key}/{loc.latitude},{loc.longitude}?exclude=alerts,hourly,minutely"
#        url = "https://api.forecast.io/forecast/{}/{},{}"
#        url = url.format(key, loc.latitude, loc.longitude)

        async with self.bot.session.get(url) as resp:
            data = await resp.json()

        try:
            tmz = pytz.timezone(data['timezone'])
        except:
            tmz = pytz.timezone("UTC")
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


    @commands.command(hidden=True)
    @commands.is_owner()
    async def wemojitest(self, ctx, *, emoji):
        try:
            emoji = int(emoji)
        except:
            pass
        msg = WEMOJI[emoji]
        await ctx.send(msg)



async def setup(bot):
    await bot.add_cog(Weather(bot))

