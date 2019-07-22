import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import pytz
try:
    import botmodules.userlocation as user
except ImportError:
    user = None


def get_sun(self, e):
    url = "https://api.forecast.io/forecast/{}/{},{}"
    apikey = self.botconfig["APIkeys"]["forecastIO_APIkey"]

    location = e.input
    if location == "" and user:
        location = user.get_location_extended(self, e.nick)
    else:
        addr, lat, lng, ctr = user.google_geocode(self, location)
        location = user.location(lat, lng, addr, ctr, e.input)

    url = url.format(apikey, location.lat, location.lng)

    response = urllib.request.urlopen(url).read().decode("utf-8", "replace")
    data = json.loads(response)
    tmz = pytz.timezone(data['timezone'])
    now = datetime.fromtimestamp(int(data['currently']['time']), tz=tmz)
    data = data['daily']['data'][0]
    sunriseobj = datetime.fromtimestamp(int(data['sunriseTime']), tz=tmz)
    sunsetobj = datetime.fromtimestamp(int(data['sunsetTime']), tz=tmz)

    sunlength = sunsetobj - sunriseobj
    if sunriseobj > now:
       ago = "from now"
       td = sunriseobj - now
    else:
       td = now - sunriseobj
       ago = "ago"
    til = self.tools['prettytimedelta'](td)
    #til = td
    sunrise = sunriseobj.strftime("%H:%M")
    sunrise = "{} ({} {})".format(sunrise, til, ago)
    if sunsetobj > now:
       ago = "from now"
       td = sunsetobj - now
    else:
       ago = "ago"
       td = now - sunsetobj
    #til = td
    til = self.tools['prettytimedelta'](td)
    sunset = sunsetobj.strftime("%H:%M")
    sunset = "{} ({} {})".format(sunset, til, ago)

    out = "[ {} ] Sunrise: {} / Sunset: {} / Day Length: {}".format(location.addr, sunrise, sunset, sunlength)
    e.output = out
    return e
get_sun.command = "!sun"

