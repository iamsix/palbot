import urllib, urllib.request, urllib.error, urllib.parse, xml.dom.minidom, socket, traceback
try: import botmodules.userlocation as user
except: pass
import re
import json


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


def get_wolfram(self, e):
    #query 'input' on wolframalpha and get the plaintext result back
    if get_wolfram.waitfor_callback:
        return
    
    try:
        location = e.location
    except:
        location = ""
    
    if location == "" and user:
        location = user.get_location(e.nick)
#        if location=="":
#            get_wolfram.waitfor_callback=True
#            user.get_geoIP_location(self, e, "", "", "", get_wolfram)
            
#            return
    address, lat, lng, country = google_geocode(self,location)

    location = urllib.parse.quote(address)

    socket.setdefaulttimeout(30)
    url = "http://api.wolframalpha.com/v2/query?appid={}&format=plaintext&input={}&location={}&latlong={},{}"
    url = url.format(self.botconfig["APIkeys"]["wolframAPIkey"],
                     urllib.parse.quote(e.input),
                     location, lat, lng)
    self.logger.debug("URL is {}".format(url))
    req = urllib.request.urlopen(url).read()
    dom = xml.dom.minidom.parseString(req)

    socket.setdefaulttimeout(10)
    if (dom.getElementsByTagName("queryresult")[0].getAttribute("success") == "false"):
        try:
            related = dom.getElementsByTagName("relatedexample")[0].getAttribute("input")
            e.input = related
            return get_wolfram(self, e)
        except Exception as inst:
            traceback.print_exc()
            print("!wolframrelated " + e.input + " : " + str(inst))
            result = self.bangcommands["!error"](self, e).output
            e.output = result
            return e
    else:
        try:
            query = dom.getElementsByTagName("plaintext")[0].childNodes[0].data
            try:
                result = dom.getElementsByTagName("plaintext")[1].childNodes[0].data
            except:
                result = self.bangcommands["!error"](self, e).output

            output = query.replace("\n", " || ") + " :: " + result.replace("\n", " || ")
            unicodes = re.findall("\\\\:[0-9a-zA-Z]{4}", output)
            if unicodes:
                print(unicodes)
                newchars = []
                for ch in unicodes:
                    ch = ch.encode().replace(b"\\:",b"\\u").decode("unicode-escape")
                    newchars.append(ch)
                output = re.sub("\\\\:[0-9a-zA-Z]{4}", "{}", output)
                output = output.format(*newchars) 
            e.output = output
            return e
        except Exception as inst:
            traceback.print_exc()
            print("!wolfram " + e.input + " : " + str(inst))
            result = self.bangcommands["!error"](self, e).output
            e.output = result
            return e
            
get_wolfram.waitfor_callback = False
get_wolfram.command = "!wolfram"
get_wolfram.helptext = "Usage: !wolfram <query>\nExample: !wolfram population of New York City\nPerforms a query through Wolfram|Alpha and returns the first result"


def calc_wolfram (self, e):
    return get_wolfram(self, e)
calc_wolfram.command = "!c"
get_wolfram.helptext = "Calculator alias for !wolfram"

def wolfram_time(self, e):
    if e.input:
        location = user.get_location(e.input)
        if location:
            e.input = "current time in %s" % location
            return get_wolfram(self, e)
    else:
        location = user.get_location(e.nick)
        if location:
            e.input = "current time in %s" % location
            return get_wolfram(self, e)
            
wolfram_time.command = "!time"
wolfram_time.helptext = "Usage: !time to get your local time, !time <nick> to get someone else's local time"
