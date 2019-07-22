import urllib.request
import urllib.parse
import json
import re


def translate(self, e):
    url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl={}&tl={}&dt=t&q={}"
    langs = re.search("(\w{2})-(\w{2})", e.input[0:5])
    if langs:
        sl = langs.group(1)
        tl = langs.group(2)
        e.input = e.input[6:]
    else:
        sl = "auto"
        tl = "en"
    url = url.format(sl, tl, urllib.parse.quote(e.input))

    opener = urllib.request.build_opener()

    opener.addheaders = [('User-Agent', "Mozilla/5.0 (X11; CrOS x86_64 12239.19.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.38 Safari/537.36")]
    response = opener.open(url).read()

    result = json.loads(response)
#    print(result)
    out = "{} ({}): {}".format(result[0][0][1], result[2], result[0][0][0])

    e.output = out
translate.command = "!translate"
