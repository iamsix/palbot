import json
import urllib.request
import urllib.error
import urllib.parse
import re


def gwiki(bot, e):
    searchterm = urllib.parse.quote("site:wikipedia.org {}".format(e.input))
    key = bot.botconfig["APIkeys"]["gsearchapi"]
    cx = bot.botconfig["APIkeys"]["gsearchcx"]
    url = 'https://www.googleapis.com/customsearch/v1?key={}&cx={}&q={}'
    url = url.format(key, cx, searchterm)
    
    try:
        request = urllib.request.Request(url, None, {'Referer': 'http://irc.00id.net'})
        response = urllib.request.urlopen(request)
    except urllib.error.HTTPError:
        bot.logger.exception("Exception in google_url:")

    results_json = json.loads(response.read().decode('utf-8'))
    results = results_json['items']

    description = results[0]['snippet']

    description = description.replace("\n", "")

    e.output = description
    
gwiki.command = "!gwiki"
gwiki.helptext = "!gwiki <query> - attempts to look up what you want to know on wikipedia using google's synopsis context"
