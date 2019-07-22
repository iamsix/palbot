import re, random


def decider(self, e):
    rps = [u"\u270A", u"\u270B", u"\u270C"]
    things = re.split(", or |, | or ", e.input, flags=re.IGNORECASE)
    if len(things) > 1: 
        e.output = "{}: {}".format(e.nick, random.choice(things).strip())
        if things[0].strip() == things[1].strip():
            e.output = "when the illusion of choice is presented choosing is meaningless"
    if e.input in rps:
        e.output = "{} : {}".format(e.nick, random.choice(rps))
        
    return e
decider.command = "bot"
