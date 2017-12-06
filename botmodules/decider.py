import re, random

def decider(self, e):
    things = re.split("or", e.input, flags=re.IGNORECASE)
    if len(things) > 1: 
        item = random.randint(0, len(things) - 1)
        e.output = "{}: {}".format(e.nick, things[item].strip())
        if things[0].strip() == things[1].strip():
            e.output = "when the illusion of choice is presented choosing is meaningless"
    return e
decider.command = "bot"
