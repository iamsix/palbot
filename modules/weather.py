import asyncio
import discord
from discord.ext import commands
import re


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

    
    @commands.command(name='w', aliases=['pw'])
    async def forecast_io(self, ctx, *, location:str = ""):
        key = self.bot.config.forecast_io_key
        loc = ctx.author_info.location
        url = f"https://api.forecast.io/forecast/{key}/{loc.latitude},{loc.longitude}"
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            weather = await self.parse_fio(data)
            if ctx.invoked_with == "w":
                await ctx.send(await self.fio_text(weather, loc))
            else:
                await ctx.send(embed=await self.fio_embed(weather, loc))


    def imperial_string_to_metric(self, line, *, both=False):
        F_C = re.compile("(-?\d+)°F")
        MI_KM = re.compile("(\d+) mph")
        def f_c(m):
            c = self.bot.utils.units.f_to_c(int(m.group(1)))
            return f"{c}°C" if not both else f"{c}°C / {m.group(0)}"

        def mi_km(m):
            km = self.bot.utils.units.mi_to_km(int(m.group(1)))
            return f"{km} km/h" if not both else f"{km} km/h / {m.group(0)}"

        line = F_C.sub(f_c, line)
        line = MI_KM.sub(mi_km, line)

        return line

    async def fio_text(self, data, loc):
        if data['feels_like_f'] == data['temp_f']:
            data['feels_like_f'] = ''
            data['feels_like_c'] = ''
        else:
            data['feels_like_f'] = f" / Feels Like: {data['feels_like_f']}"
            data['feels_like_c'] = f" / Feels Like: {data['feels_like_c']}"
        
        out = f"{loc.formatted_address} / "
        if loc.country == "United States":
            out += ("{condition} {condition_icon} / {temp_f} ({temp_c}){feels_like_f} / "
                    "Humidity: {humidity} / Wind: {wind_direction} at {wind_speed_mi} / "
                    "Cloud Cover: {cloud_cover} / High: {high_f} Low: {low_f} / "
                    "Outlook: {outlook_imperial}").format(**data)
        else:
            out += ("{condition} {condition_icon} / {temp_c} ({temp_f}){feels_like_c} / "
                    "Humidity: {humidity} / Wind: {wind_direction} at {wind_speed_km} / "
                    "Cloud Cover: {cloud_cover} / High: {high_c} Low: {low_c} / "
                    "Outlook: {outlook_metric}").format(**data)

        return out

    async def fio_embed(self, data, loc):
        wicons = "https://raw.githubusercontent.com/iamsix/palbot/rewrite/utils/wicons/{}.png"
        e = discord.Embed(title=f"{loc.formatted_address} - {data['condition']}")
        e.set_footer(text=self.imperial_string_to_metric(data['outlook_imperial'], both=True))
        e.set_thumbnail(url=wicons.format(data['condition_icon']))
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
            outlook_imp = f"{data['hourly']['summary']} {data['daily']['summary']}"
        outlook_metric = self.imperial_string_to_metric(outlook_imp)

        temp_c = f"{units.f_to_c(current['temperature'])}°C"
        temp_f = f"{int(round(current['temperature'],0))}°F"
        feels_like_c = f"{units.f_to_c(current['apparentTemperature'])}°C"
        feels_like_f = f"{int(round(current['apparentTemperature'],0))}°F"

        low_c = f"{units.f_to_c(data['daily']['data'][0]['temperatureMin'])}°C"
        low_f = f"{int(round(data['daily']['data'][0]['temperatureMin'],0))}°F"
        high_c = f"{units.f_to_c(data['daily']['data'][0]['temperatureMax'])}°C"
        high_f = f"{int(round(data['daily']['data'][0]['temperatureMax'],0))}°F"

        weather = {'condition': current['summary'],
                   'condition_icon': WEMOJI.get(current['icon'], ''),
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
                   'high_f' : high_f
                   }
        return weather


    



def setup(bot):
    bot.add_cog(Weather(bot))

