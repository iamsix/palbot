import discord
from discord.ext import commands
import asyncio
import re
from urllib.parse import quote as uriquote
import datetime
import pytz

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
        async with self.bot.session.get(url) as resp:
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

        url = "https://api.overwatchleague.com/live-match"
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            data = data['data']

        tz = ctx.author_info.timezone if ctx.author_info.timezone else "US/Eastern"

        output = ""
        if data['liveMatch']:
            match = data['liveMatch']
            if match['status'] == "PENDING":
                output = self.format_pending_game(match, tz)
            else:
                game = None
                for g in match['games']:
                    if g['status'] == "IN_PROGRESS":
                        game = g['number']
                if game:
                    status = "Map {} of {}".format(game,
                            match['conclusionValue'])
                else:
                    status = "Intermission"
                fmt = "{} {} - {} {} ({})"
                output = fmt.format(match['competitors'][0]['name'],
                                    match['scores'][0]['value'],
                                    match['scores'][1]['value'],
                                    match['competitors'][1]['name'],
                                    status)
        if data['nextMatch']:
            match = data['nextMatch']
            output += " | {}".format(self.format_pending_game(match, tz))
        
        if output:
            await ctx.send(output)

    def format_pending_game(self, match, tz):
        starttime = datetime.datetime \
                            .strptime(match['startDate'],
                                    "%Y-%m-%dT%H:%M:%S.%fZ") \
                            .replace(tzinfo=pytz.utc) \
                            .astimezone(tz=pytz.timezone(tz))

        status = starttime.strftime('%-d %b at %-I:%M%p').replace(':00', '')

        fmt = "{} vs {} ({} {})"
        return fmt.format(match['competitors'][0]['name'],
                                match['competitors'][1]['name'],
                                status, starttime.tzname())


def setup(bot):
    bot.add_cog(Games(bot))