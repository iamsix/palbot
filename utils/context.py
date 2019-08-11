import sqlite3
from discord.ext import commands


class MoreContext(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def author_info(self):
        return AuthorInfo(self.author.id)

#@dataclass
class Location:
    def __init__(self, latitude, longitude, city, local_area, country, user_input_location):
        self.latitude = latitude
        self.longitude = longitude
        self.city = city
        self.local_area = local_area
        self.country = country
        self.user_input_location = user_input_location
        # convenience method for formatted "Ciy, ST" or "City, Country"

class AuthorInfo:
    def __init__(self, user_id):

        self.user_id = user_id

        self.conn = sqlite3.connect('userinfo.sqlite')
        self.c = self.conn.cursor()
        result = self.c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='userinfo';").fetchone()
        if not result:
            # add a username field just for convenience? don't actually query it
            c.execute('''CREATE TABLE userinfo (user integer, username text, field text, data text);''')
            self.conn.commit()

    @property
    def location(self):
        # consider json with a single location field?
        q = '''SELECT field, data FROM userinfo WHERE user = (?) AND
               (field = 'latitude' OR field = 'longitude' OR field = 'city'
               OR field = 'local_area' OR field = 'country'
               OR field = 'user_input_location');'''
        result = self.c.execute(q, (self.user_id,))

        loc = {}
        for field, data in result:
            loc[field] = data

        return Location(**loc) if loc else None


    @property
    def birthday(self):
        q = '''SELECT data from userinfo WHERE user = (?) AND field = 'birthday'; '''
        bd = self.c.execute(q, (self.user_id,)).fetchone()
        if bd:
            return bd[0]


    @property
    def timezone(self):
        q = '''SELECT data from userinfo WHERE user = (?) AND field = 'timezone'; '''
        tz = self.c.execute(q, (self.user_id,)).fetchone()
        if tz:
            return tz[0]

    @property
    def strava(self):
        q = '''SELECT data from userinfo WHERE user = (?) AND field = 'strava'; '''
        strava = self.c.execute(q, (self.user_id,)).fetchone()
        if strava:
            return strava[0]

    @property
    def lastfm(self):
        q = '''SELECT data from userinfo WHERE user = (?) AND field = 'lastfm'; '''
        lastfm = self.c.execute(q, (self.user_id,)).fetchone()
        if lastfm:
            return lastfm[0]



