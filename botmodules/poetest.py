from poe import Client
import poe.utils as utils
from io import BytesIO
import discord
import asyncio


def poe(self, e):
    where = "%{}%".format(e.input)
    item = Client().find_items({'_pageName': where}, limit=1)
    if not item:
        return
#    print(item[0])
#    print(dir(item[0]))
    result = item[0]
    if result.base == "Prophecy":
        flavor = 'prophecy'
    elif 'gem' in result.tags:
        flavor = 'gem'
        # do some meta stufff here maybe?
    elif 'divination_card' in result.tags:
        flavor = 'unique'
        # possibly needs more here
    else:
        flavor = result.rarity
    r = utils.ItemRender(flavor)
    image = r.render(result)
    image_fp = BytesIO()
    image.save(image_fp, 'png')
    image_fp.seek(0)

    asyncio.ensure_future(self.send_file(e.source, image_fp, filename=result.name + ".png"))



#def e():
#    pass
#e.input = "lifesprig"

#poe(None, e)
poe.command = "!poe"
