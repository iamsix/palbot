import discord
from discord.ext import commands
import asyncio
import re
from urllib.parse import quote as uriquote
import datetime
import pytz
import json
from utils.time import HumanTime

from poe import Client
import poe.utils as poeutils
from io import BytesIO


class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.CARD_REGEX = re.compile(r"\[([^\(]*?)(?:\((.*?)\))?\]")

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

    async def friendly_date(self, ctx, date):
        if not date:
            if ctx.author_info.timezone:
                return datetime.datetime.now(pytz.timezone(ctx.author_info.timezone))
            else:
                return datetime.datetime.now(pytz.timezone("US/Eastern"))
        else:
            return date.dt

    @commands.command()
    async def owl(self, ctx, *, date: HumanTime = None):
        """Show the live overwatch league matches and scores"""
        now = await self.friendly_date(ctx, date)

        url = "https://overwatchleague.com/en-us/schedule"
        page = await self.bot.utils.bs_from_url(self.bot, url)
        jsonhtml = page.find('script', id='__NEXT_DATA__')
        data = json.loads(jsonhtml.string)
        try:      
            matches = data['props']['pageProps']['blocks'][2]['scheduleV2']['matchSegments'][0]['matches']
            # matches[0] = Pending
            # matches[1] = In progress
            # matches[2] = Complete
            out = []
            for match in matches[0]['data'] + matches[1]['data'] + matches[2]['data']:
                date = datetime.datetime.fromtimestamp(match['startDate']/1000, tz=now.tzinfo)
                if date.date() != now.date():
                    continue
                teams = match['competitors']
                line = ""
                if match['status'] == 'PENDING':
                    line = f"{teams[0]['name']} - {teams[1]['name']} : {date.strftime('%-I:%M%p')}"
                if match['status'] == 'IN_PROGRESS':
                    if not match['scores']:
                        # TODO look for the IsEncore thing and make a special status for it
                        continue
                    line = f"{teams[0]['name']} {match['scores'][0]} - {match['scores'][1]} {teams[1]['name']} : Live"
                if match['status'] == 'CONCLUDED':
                    line = f"{teams[0]['name']} {match['scores'][0]} - {match['scores'][1]} {teams[1]['name']} : End"
                if line:
                    out.append(line)

            if not out:
                await ctx.send(f"Doesn't appear to be any games on {now.date()}")
            else:
                await ctx.send("```{}```".format("\n".join(out)))
        except:
            await ctx.send(f"Either there's no games on {now.date()} or the OWL site broke this")





async def setup(bot):
    await bot.add_cog(Games(bot))
