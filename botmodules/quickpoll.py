def quickpoll(self, e):
    e.reaction = ["✅", "❌"]
    return e

quickpoll.command = "!qp"


#async def canada(self, e):
#     if "canada" in e.input.lower():
#        e.reaction = ["🇨🇦", "🇦"]

#canada.lineparser = True

#async def murica(self, e):
#     if "america" in e.input.lower():
#        e.reaction = ["🇫", "🇺", "🇨", "🇰", "🇾", "🇪", "🇦", "🇭", "🇺🇸"]
#murica.lineparser = True
