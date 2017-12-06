import sqlite3, urllib.parse, urllib.request, json


def set_location(self, e):
    save_location(self, e.nick, e.input)
    
def save_location(self, nick, loc):
    conn = sqlite3.connect('userlocations.sqlite')
    c = conn.cursor()
    result = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='userlocations';").fetchone()
    if not result:
        c.execute('''create table userlocations(user text UNIQUE ON CONFLICT REPLACE, location text,
        lat DECIMAL, long DECIMAL, address text, country text)''')
        
    # we need to geocode this to get extended data
    formatted_address, lat, lng, country = google_geocode(self, loc)
        
    c.execute("""insert into userlocations values (?,?,?,?,?,?)""", (nick, loc, lat, lng, formatted_address, country))
    
    conn.commit()
    c.close()

set_location.command = "!setlocation"
set_location.helptext = """Usage: !setlocation <location>
Example: !setlocation hell, mi
Saves your geographical location in the bot.
Useful for the location based commands (!sunset, !sunrise, !w).
Once your location is saved you can use those commands without an argument."""
    
def get_location(nick):
    conn = sqlite3.connect('userlocations.sqlite')
    c = conn.cursor()
    result = c.execute("SELECT location FROM userlocations WHERE UPPER(user) = UPPER(?)", [nick]).fetchone()
    if result:
        return result[0]
    else:
        return ""
    
def get_location_extended(self, nick):
    # check if the data is complete - if not query it and save it
    conn = sqlite3.connect('userlocations.sqlite')
    c = conn.cursor()
    query = "SELECT location, lat, long, address, country FROM userlocations WHERE UPPER(user) = UPPER(?)"
    result = c.execute(query, [nick]).fetchone()
    if result:
        if not result[1]:
            # this is old location data, so we need to geocode it and save it.
            save_location(self, nick, result[0])
            result = c.execute(query, [nick]).fetchone()
            if not result[1]:
                return None
        return location(result[1], result[2], result[3], result[4], result[0])
    else:
        return None
    

class location:
    def __init__(self, lat, lng, addr, country, userinputlocation):
        self.lat = lat
        self.lng = lng
        self.addr = addr
        self.country = country
        self.userinputlocation = userinputlocation


def google_geocode(self, address):
    gapikey = self.botconfig["APIkeys"]["shorturlkey"] #This uses the same Google API key as URL shortener
    address = urllib.parse.quote(address)

    url = "https://maps.googleapis.com/maps/api/geocode/json?address={}&key={}"
    url = url.format(address, gapikey)


    try:
        request = urllib.request.Request(url, None, {'Referer': 'http://irc.00id.net'})
        response = urllib.request.urlopen(request)
    except urllib.error.HTTPError as err:
        self.logger.exception("Exception in google_geocode:")

    try:
        results_json = json.loads(response.read().decode('utf-8'))
        status = results_json['status']

        if status != "OK":
            raise

        city, state, country, poi = "","","", ""
        
        for component in results_json['results'][0]['address_components']:
            if 'locality' in component['types']:
                city = component['long_name']
            elif 'point_of_interest' in component['types'] or 'natural_feature' in component['types']:
                poi = component['long_name']
            elif 'administrative_area_level_1' in component['types']:
                state = component['short_name']
            elif 'country' in component['types']:
                if component['short_name'] != "US":                
                    country = component['long_name']
                else:
                    country = False

        if not city:
            city = poi #if we didn't find a city, maybe there was a POI or natural feature entry, so use that instead

        if not country: #Only show the state if in the US
            country == ""
        elif country != "Canada" and city:               #We don't care about provinces outside of the US and Canada, unless the city name is empty
            state = ""

        if city:
            formatted_address = "{}{}{}".format(city,"" if not state else ", " + state,"" if not country else ", " + country)
        elif state:
            formatted_address = "{}{}".format(state,"" if not country else ", " + country)
        else:
            formatted_address = "{}".format("" if not country else country)
        
        
        lng = results_json['results'][0]['geometry']['location']['lng']
        lat = results_json['results'][0]['geometry']['location']['lat']


        
    except:
        self.logger.exception("Failed to geocode location using Google API:")

        return
    
    return formatted_address, lat, lng, country
    

def get_geoIP_location(self, e="", ip="", nick="", whois_reply=False, callback=""): 
# This function gets called twice so we need to account for the different calls
# It gets called once by a server side event
# then again when the server responds with the whois IP information
    ##import pdb; pdb.set_trace()
    if callback:
        get_geoIP_location.callback = callback

    

    if whois_reply and get_geoIP_location.callback:

        #we're basically doing a fake call to the original requestor function
        #We set the <arg> portion of !command <arg> to give it expected input
        # GeoIP URL is http://freegeoip.net/json/<ip>
        
        get_geoIP_location.callback.waitfor_callback=False
        ##import pdb; pdb.set_trace()
        e.location = get_geoIP(ip)
        response = get_geoIP_location.callback(self, e)
        self.botSay(response) #since this is a callback, we have to say the line ourselves
        
    elif whois_reply:
        e.output = get_geoIP(ip)
        self.botSay(e)
    elif not callback:
        try: 
            #Try to look up an IP address that was given as a command arugment
            #If that fails, fall back to whois info    
            if e.input:
                e.output = get_geoIP(e.input)
                self.botSay(e)
                return
            else:
                request_whoisIP(self, get_geoIP_location, nick, e)    
        except:
            pass
    else:
        request_whoisIP(self, get_geoIP_location, nick, e)
    
get_geoIP_location.command = "!geoip"
get_geoIP_location.callback = None
get_geoIP_location.helptext = "Looks up your IP address and attempts to return a location based on it."

def get_geoIP(ip):
    location = get_geoIP_free(ip)
    if location:
        return location
    #import pdb; pdb.set_trace()
    location = get_geoIP_netimpact(ip)
    if location:
        return location

    
def get_geoIP_free(ip):
    ip = urllib.parse.quote(ip)
    
    url = "http://freegeoip.net/json/{}".format(ip)

    response = urllib.request.urlopen(url).read().decode('utf-8')

    try:
        response = urllib.request.urlopen(url).read().decode('utf-8')
        geoip = json.loads(response)
    except:
        return False

    if geoip['city']:
        return "%s, %s" % (geoip['city'], geoip['region_name'])
    else:
        return False

def get_geoIP_netimpact(ip):

#http://api.netimpact.com/qv1.php?key=WdpY8qgDVuAmvgyJ&qt=geoip&d=json&q=<ip>
    ip = urllib.parse.quote(ip)

    url = "http://api.netimpact.com/qv1.php?key=WdpY8qgDVuAmvgyJ&qt=geoip&d=json&q={}".format(ip)
    try:
        response = urllib.request.urlopen(url).read().decode('utf-8')
        geoip = json.loads(response)[0]
    except:
        return False

    if geoip:
        return "%s, %s, %s" % (geoip[0], geoip[1], geoip[2])
    else:
        return False


def request_whoisIP(self, reply_handler, nick="", e=""):
    #import pdb; pdb.set_trace()
# This function sends the whois request and registers the response handler    
# We also need to store the source event that triggered the whois request     
# So we can respond back to it properly
# Or if we are internally getting whois info, we don't need to know about the source event

    if nick:
        self.irccontext.whois(nick)
    elif e:
        self.irccontext.whois(e.nick)
    else:
        return
    self.whoisIP_reply_handler = reply_handler
    self.whoisIP_sourceEvent = e


