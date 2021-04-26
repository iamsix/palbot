import discord
from discord.ext import commands
import asyncio
import re
from urllib.parse import quote as uriquote
import datetime
import pytz
import json

from poe import Client
import poe.utils as poeutils
from io import BytesIO


class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.CARD_REGEX = re.compile("\[([^\(]*?)(?:\((.*?)\))?\]")

    @commands.command()
    async def mtg(self, ctx, *, card: str):
        """Search for and post an MTG <card>"""
        card = f'[{card}]'
        card, cset = self.CARD_REGEX.findall(card)[0]
        data = await self.get_card(card, cset)
        e = discord.Embed(title=f"{data['name']} ({data['set']})")
        e.set_image(url=data['imageUrl'])
        await ctx.send(embed=e)

    async def get_card(self, card, cset=""):
        card = uriquote(card.strip())
        cset = uriquote(cset.strip())

        url = f"http://api.magicthegathering.io/v1/cards?name={card}"
        if cset:
            url += f"&set={cset}"

        headers = {'User-agent': 'Palbot for discord/2.0'}
        async with self.bot.session.get(url, headers=headers) as resp:
            data = await resp.json()
            cards = data['cards']
        
        if not cards:
            return None
        data = None
        for card in cards:
            if "imageUrl" in card:
                data = card
                break
        return data

    @commands.command()
    async def poe(self, ctx, *, item: str):
        """Search for and post a POE <item> image"""
        item = Client().find_items({'_pageName': f'%{item}%'}, limit=1)
        if not item:
            return

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
        r = poeutils.ItemRender(flavor)
        image = r.render(result)
        image_fp = BytesIO()
        image.save(image_fp, 'png')
        image_fp.seek(0)

        await ctx.send(file=discord.File(image_fp, result.name + ".png"))

    @commands.command()
    async def owl(self, ctx):
        """Show the live overwatch league matches and scores"""

        if ctx.author_info.timezone:
            now = datetime.datetime.now(pytz.timezone(ctx.author_info.timezone))
            nowtz = pytz.timezone(ctx.author_info.timezone)
        else:
            now = datetime.datetime.now(pytz.timezone("US/Eastern"))
            nowtz = pytz.timezone("US/Eastern")


        url = "https://overwatchleague.com/en-us/schedule"
        page = await self.bot.utils.bs_from_url(self.bot, url)
        jsonhtml = page.find('script', id='__NEXT_DATA__')
        data = json.loads(jsonhtml.string)
#        matches = data['props']['pageProps']['blocks'][0]['owlHeader']['scoreStripList']['scoreStrip']['matches']
        matches = data['props']['pageProps']['blocks'][2]['schedule']['tableData']['events'][0]['matches']

        out = []
        for match in matches:
            date = datetime.datetime.fromtimestamp(match['startDate']/1000, tz=nowtz)
            if date.date() != now.date():
                continue
            teams = match['competitors']
            line = ""
            if match['status'] == 'PENDING':
                line = f"{teams[0]['name']} - {teams[1]['name']} : {date.strftime('%-I:%M%p')}"
            if match['status'] == 'IN_PROGRESS':
                line = f"{teams[0]['name']} {match['scores'][0]} - {match['scores'][1]} {teams[1]['name']} : Live"
            if match['status'] == 'CONCLUDED':
                line = f"{teams[0]['name']} {match['scores'][0]} - {match['scores'][1]} {teams[1]['name']} : End"
            if line:
                out.append(line)

        if out:
            await ctx.send("```{}```".format("\n".join(out)))
        else:
            await ctx.send("Either there's no games today or the OWL site broke this")





def setup(bot):
    bot.add_cog(Games(bot))
