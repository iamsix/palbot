import sqlite3
from discord.ext import commands
from urllib.parse import quote as uriquote
import json


class MoreContext(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.override_send_for_edit = None
        
    async def send(self, *args, **kwargs):
        paginator = kwargs.pop('paginator', None)
        if not self.override_send_for_edit or not self.message.id == self.override_send_for_edit[0].id:
            result = await super().send(*args, **kwargs)
            self.bot.recent_posts.append((self.message, result, paginator))
            return result
        else:
            edit = self.override_send_for_edit[1]
            self.override_send_for_edit = None
            if len(args):
                kwargs['content'] = args[0]
                if 'embed' not in kwargs:
                    kwargs['embed'] = None
            await edit.edit(**kwargs)
            return edit
        
    @property
    def author_info(self):
        return AuthorInfo(self.author)


#class myHelp(commands.HelpCommand):
#    def __init__(self):
#        super().__init__(command_attrs={
#            'cooldown': commands.Cooldown(1, 3.0, commands.BucketType.member),
#            'help': 'Shows help about the bot, a command, or a category'
#        })

#@dataclass
class Location:
    def __init__(self, latitude, longitude, city, local_area, country, user_input_location):
        self.latitude = latitude
        self.longitude = longitude
        self.city = city
        self.local_area = local_area
        self.country = country
        self.user_input_location = user_input_location
        #

    @classmethod
    async def convert(cls, ctx, address):
        if not address and ctx.author_info.location:
            return ctx.author_info.location
        elif not address:
            raise commands.MissingRequiredArgument
        else:
            loc = cls.from_google_geocode(ctx.bot, address)
            if not loc:
                raise commands.BadArgument
            return loc

    @property
    def formatted_address(self):
        '''convenience method for formatted "Ciy, ST" or "City, Country"'''
        if self.country == "United States":
            return f"{self.city}, {self.local_area}"
        elif self.country == "Canada":
            return f"{self.city}, {self.local_area}, {self.country}"
        else:
            return f"{self.city}, {self.country}"

    async def get_timezone(self, bot):
        key = bot.config.timezonedb
        url = (f"http://api.timezonedb.com/v2.1/get-time-zone?key={key}"
               f"&format=json&by=position&lat={self.latitude}&lng={self.longitude}")
        async with bot.session.get(url) as resp:
            results = await resp.json()
            #not sure why they \escape a '/' char... pytz doesnt like it..
            zone = results['zoneName'].replace('\\', '')
            return zone


    @classmethod
    async def from_google_geocode(cls, bot, address):
        url = "https://maps.googleapis.com/maps/api/geocode/json?address={}&key={}"
        url = url.format(uriquote(address), bot.config.gsearch2)

        async with bot.session.get(url) as resp:
            results_json = await resp.json()
            status = results_json['status']

            if status != "OK":
                return None
            city, state, country, poi = "","","", ""

            for component in results_json['results'][0]['address_components']:
                if not city and 'sublocality' in component['types']:
                    city = component['long_name']
                if 'locality' in component['types']:
                    city = component['long_name']
                elif 'point_of_interest' in component['types'] or 'natural_feature' in component['types']:
                    poi = component['long_name']
                elif 'administrative_area_level_1' in component['types']:
                    state = component['short_name']
                elif 'country' in component['types']:
                    country = component['long_name']

            if not city:
                city = poi #if we didn't find a city, maybe there was a POI or natural feature entry, so use that instead

            lng = results_json['results'][0]['geometry']['location']['lng']
            lat = results_json['results'][0]['geometry']['location']['lat']

            loc = cls(lat, lng, city, state, country, address)

            return loc

    @classmethod
    async def get_location_by_latlon(cls, bot, lat, lon):
        location_string = None
        url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={bot.config.gsearch2}"
        city, state = "", ""
        async with bot.session.get(url) as resp:
            if resp.status == 200:
                resp_json = await resp.json()
                if len(resp_json['results']) > 0 and len(resp_json['results'][0]['address_components']) > 0:
                    location = resp_json['results'][0]
                else:
                    print(f"Google maps did not return at least one location for coordinates: {lat},{lon}")
                    return None
                try:
                    for pt in location['address_components']:
                        if "locality" in pt['types'] or 'sublocality' in pt['types']:
                            city = pt['long_name']
                        if "administrative_area_level_1" in pt['types']:
                            state = pt['short_name']
                    if city or state:
                        location_string = f"{city}, {state}"
                except KeyError as e:
                    print(f"Google maps API did not return proper response: {e} is missing")
            else:
                print(f"get_location_by_latlon error: {resp.status}")
        return location_string

class AuthorInfo:
    def __init__(self, user):

        self.user_id = user.id
        self.user = user

        self.conn = sqlite3.connect('userinfo.sqlite')
        self.c = self.conn.cursor()
        # username field is never queried, just exists for convenient lookup when manually checking db entries
        self.c.execute('''CREATE TABLE IF NOT EXISTS userinfo (user integer, username text, field text, data text);''')
        self.conn.commit()

    def single_getter(self, key):
        q = '''SELECT data FROM userinfo WHERE user = (?) AND field = (?); '''
        result = self.c.execute(q, (self.user_id, key)).fetchone()
        if result:
            return result[0]
        else:
            return None

    def single_setter(self, key, value):
        q = '''SELECT data FROM userinfo WHERE user = (?) AND field = (?); '''
        result = self.c.execute(q, (self.user_id, key)).fetchone()
        # Unfortunately key-value db means I can't INSERT OR REPLACE
        if result:
            q = '''UPDATE userinfo SET data = (?) WHERE user = (?) AND field = (?); '''
            self.c.execute(q, (value, self.user_id, key))
        else:
            q = '''INSERT INTO userinfo VALUES (?, ?, ?, ?); '''
            self.c.execute(q, (self.user_id, str(self.user), key, value))
        self.conn.commit()
 


    @property
    def location(self):
        q = '''SELECT field, data FROM userinfo WHERE user = (?) AND
               (field = 'latitude' OR field = 'longitude' OR field = 'city'
               OR field = 'local_area' OR field = 'country'
               OR field = 'user_input_location');'''
        result = self.c.execute(q, (self.user_id,))

        loc = {}
        for field, data in result:
            loc[field] = data

        return Location(**loc) if loc else None

    @location.setter
    def location(self, loc: Location):
        for k,v in loc.__dict__.items():
            self.single_setter(k, v)
    
    @property
    def id(self):
        return self.user_id

    @property
    def birthday(self):
        return self.single_getter('birthday')
    @birthday.setter
    def birthday(self, user_input_birthday: str):
        self.single_setter('birthday', user_input_birthday)

    @property
    def timezone(self):
        return self.single_getter('timezone')
    @timezone.setter
    def timezone(self, tz_name: str):
        self.single_setter('timezone', tz_name)
        
    @property
    def strava(self) -> int:
        return int(self.single_getter('strava'))
    @strava.setter
    def strava(self, uid: str):
        # When setting this we must clear the athlete info
        self.strava_athlete = None
        self.single_setter('strava', uid)


    # technically this makes the strava uid partially redundant.
    @property
    def strava_athlete(self):
        athlete = self.single_getter('strava_athlete')
        if athlete:
            athlete = json.loads(athlete)
        return athlete
    @strava_athlete.setter
    def strava_athlete(self, athlete):
        self.single_setter('strava_athlete',
                           json.dumps(athlete))

    @property
    def lastfm(self):
        return self.single_getter('lastfm')
    @lastfm.setter
    def lastfm(self, uid: str):
        self.single_setter('lastfm', uid)
