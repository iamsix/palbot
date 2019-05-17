import urllib.parse
import json
import re


def get_urbandictionary(self, e):
    searchterm = e.input
    
    if searchterm == "wotd":
        e.output = get_urbandictionary_wotd(self)
        return e

    #super smrt AI code to tell if you want a different definition
    #We only get the first 9 results.
    number = re.search("-[1-9]", searchterm[0:2])
    if number and len(searchterm.split(" ")) > 1:
       searchterm = searchterm[3:]
       number = int(number.group(0)[1:2]) - 1
    else:
       number = 0

    url = "http://api.urbandictionary.com/v0/define?term={}".format(urllib.parse.quote(searchterm))

    if searchterm == "":
        url = "http://api.urbandictionary.com/v0/random"

    data = urllib.request.urlopen(url).read().decode()
    data = json.loads(data)['list'][number]
    
    definition = data['definition'].replace('[','').replace(']','')
    definition = definition.replace("\n",' ')
    o = f"{data['word']}: {definition} [ {data['permalink']} ]".format()

    e.output = o
    return e

get_urbandictionary.command = "!ud"
get_urbandictionary.helptext = """Usage: !ud <word or phrase>
Example: !ud hella
Shows urbandictionary definition of a word or phrase.
!ud alone returns a random entry
!ud wotd returns the current word of the day"""


def get_urbandictionary_wotd(self):

    url = "http://www.urbandictionary.com"
    page = self.tools["load_html_from_URL"](url)
    first_definition = ""

    first_word = page.findAll('a', attrs={"class": "word"})[0].string
    first_word = first_word.encode("utf-8", 'ignore')

    for content in page.findAll('div', attrs={"class": "meaning"})[0].contents:
        if content.string is not None:
            first_definition += content.string

#    first_definition = tools.decode_htmlentities(first_definition)
    first_definition = first_definition.replace("\n", " ")

    wotd = (first_word.decode('utf-8') + ": " + first_definition + " [ %s ]" % self.tools['shorten_url'](url))

    return wotd
