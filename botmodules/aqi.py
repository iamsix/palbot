import json
import urllib.request
try:
    import botmodules.userlocation as user
except ImportError:
    user = None
pass


def get_aqi(self, e):
    if user and not e.input:
        try:
            lat, lng, _, _ = user.get_location_extended(self, e.nick)
            loc = "geo:{};{}".format(lat, lng)
        except Exception as ex:
            e.output = "No user location found"
            return e
    elif e.input[-1] == "!":
        # force location by name
        loc = e.input[:-1]
    elif e.input:
        _, lat, lng, _ = user.google_geocode(self, e.input)
        loc = "geo:{};{}".format(lat, lng)

    url = "http://api.waqi.info/feed/{}/?token={}"
    url = url.format(loc, self.botconfig["APIkeys"]["aqicn"])

    data = urllib.request.urlopen(url).read().decode()
    data = json.loads(data)
    if data['status'] != "ok":
        print(data)
        return
    data = data['data']
    
    pm25 = data['iaqi']['pm25']['v']

    if pm25 < 50:
        condition = " (Good)"
    elif pm25 < 101:
        condition = " (Moderate)"
    elif pm25 < 151:
        condition = " (Unhealthy for sensitive groups)"
    elif pm25 < 201:
        condition = " (Unhealthy)"
    elif pm25 < 301:
        condition = " (Very Unhealthy)"
    elif pm25 > 300:
        condition = " (Hazardous)"
    else:
        condition = ""

    city = data['city']['name']
    out = "{} - Air Quality: PM2.5: {}{}".format(city, pm25, condition)

    try:
        o3 = pm25 = data['iaqi']['o3']['v']
        out += " Ozone: {}".format(o3)
    except:
        pass


    e.output = out

    return e

get_aqi.command = "!aqi"

