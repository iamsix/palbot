import re
import urllib.request
import urllib.parse
import json


def card_scraper (self, e, test=False):
    if e.source.name != "mtg_nerds":
        return
    CARDREGEX = "\[([^\(]*?)(?:\((.*?)\))?\]"
    cards = re.findall(CARDREGEX, e.input)

    for card, set in cards:
        card = urllib.parse.quote(card.strip())
        set = urllib.parse.quote(set.strip())

        if set:
            url = "http://api.magicthegathering.io/v1/cards?name={}&set={}".format(card, set)
        else:
            url = "http://api.magicthegathering.io/v1/cards?name={}".format(card)

        try:
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-agent', 'Palbot for discord/2.0')]
            response = opener.open(url).read()
        except urllib.error.HTTPError as e:
            print(e)
            print(e.read())
        data = response.decode()

        cards = json.loads(data)['cards']
        if not cards:
            e.output += "No card found for [{}]\n".format(card)
            continue

        data = None
        image = "No image found"
        for card in cards:
            try:
                image = card["imageUrl"]
                data = card
                break
            except KeyError:
                pass


        e.output += "**{}** ({}) \n {} \n".format(data["name"],
                                                  data["set"],
                                                  image)

    e.allowembed = True
    print(e.output)
    return e
card_scraper.lineparser = True

class e:
    pass
e.source = e
e.source.name = "mtg_nerds"
e.input = "check out the [hinder (chk)] to [tunnel vision] combo"
e.output = ""
card_scraper(None, e, True)
