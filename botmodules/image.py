import urllib.request, urllib.error, urllib.parse
import json

def image_search(self, e):
    searchterm = urllib.parse.quote(e.input)
    key = self.botconfig["APIkeys"]["ischapi"]
    cx = self.botconfig["APIkeys"]["gsearchcx"]
    url = 'https://www.googleapis.com/customsearch/v1?key={}&cx={}&q={}&searchType=image'
    url = url.format(key, cx, searchterm)
    if e.source.name != "nsfw":
        url += "&safe=medium"

    try:
        request = urllib.request.Request(url, None, {'Referer': 'http://irc.00id.net'})
        response = urllib.request.urlopen(request)
    except urllib.error.HTTPError as err:
        self.logger.exception("Exception in google_url: {}".format(err))
        self.logger.exception("Body is: {}".format(err.read()))

    results_json = json.loads(response.read().decode('utf-8'))
    results = results_json['items']

    e.output = results[0]['link']
    e.allowembed = True
    return e

image_search.command = "!image"
