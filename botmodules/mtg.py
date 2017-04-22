import re
import urllib.request
import urllib.parse
import json


def card_scraper (self, e):
    if e.source.name != "mtg_nerds":
        return

    CARD_REGEX = "\[([^\(]*?)(?:\((.*?)\))?\]"
    cards = re.findall(CARD_REGEX, e.input)

    for card, cset in cards:
        e.output += get_card(card, cset)
    e.allowembed = True
    return e
card_scraper.lineparser = True

def mtg_cmd (self, e):
    card = e.input.strip()
    cset = ""
    cres = re.search("\s\(([A-z]+)\)", e.input)
    if cres:
        cset = cres.group(1).strip()
        card = card.replace(cres.group(0), "").strip()

    e.output = get_card(card, cset)
    e.allowembed = True
    return e
mtg_cmd.command = "!mtg"        

def get_card (card, cset=""):
        card = urllib.parse.quote(card.strip())
        cset = urllib.parse.quote(cset.strip())

        url = "http://api.magicthegathering.io/v1/cards?name={}".format(card)
        if cset:
            url += "&set={}".format(cset)

        try:
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-agent', 'Palbot for discord/2.0')]
            response = opener.open(url).read()
        except urllib.error.HTTPError as err:
            print(err)
            print(err.read())
        data = response.decode()

        cards = json.loads(data)['cards']
        if not cards:
            return "No card found for [{}]\n".format(card)

        data = None
        image = "No image found"
        for card in cards:
            try:
                image = card["imageUrl"]
                data = card
                break
            except KeyError:
                pass


        return "**{}** ({}) \n {} \n".format(data["name"],
                                             data["set"],
                                             image)


class test:
    pass
test.source = test
test.source.name = "mtg_nerds"
test.input = "check out the [hinder (chk)] to [tunnel vision] combo"
test.output = ""
card_scraper(None, test)
print("card scraper test:")
print(test.output)
print("----")
test.input = "hinder (chk)"
mtg_cmd(None, test)
print(test.output)
