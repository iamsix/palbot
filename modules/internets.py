import discord
from discord.ext import commands
from urllib.parse import quote as uriquote
from utils.paginator import Paginator
import json
import asyncio
import re
from datetime import datetime
import html2text

class Internets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    UDREGEX = re.compile(r'(\[(.+?)\])')

    @commands.command(name='ud')
    async def urban_dictionary(self, ctx, *, term:str = ""):
        """Searches for a term on urbandictionary.com"""
        if not term:
            url = "http://api.urbandictionary.com/v0/random"
        else:
            term = uriquote(term)
            url = f"http://api.urbandictionary.com/v0/define?term={term}"

        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            pages = Paginator(ctx, data['list'], self.ud_callback)
            await pages.paginate()

    async def ud_callback(self, data, pg_number):
        reply = await self.parse_ud(data[pg_number])
        reply.title += f" ({pg_number+1} of {len(data)})"
        return None, reply

    async def parse_ud(self, data):
        def repl(m):
            word = m.group(2)
            return f'[{word}](http://{word.replace(" ", "-")}.urbanup.com)'

        e = discord.Embed(title=data['word'], url=data['permalink'])

        definition = re.sub(self.UDREGEX, repl, data['definition'])
        e.description = definition

        try:
            stamp = datetime.strptime(data['written_on'][:10],"%Y-%m-%d")
            e.timestamp = stamp
        except:
            pass

        return e


    @commands.command(name="wiki")
    async def wikipedia(self, ctx, *, term:str = ""):
        """Search for a term on wikipedia and return a snippet"""
        if not term:
             url = "http://en.wikipedia.org/wiki/Special:Random"
        else:
            url = await self.bot.utils.google_for_urls(self.bot,
                    f"site:wikipedia.org {term}",
                    url_regex="wikipedia.org/wiki")

        if url and "File:" in url[0]:
            return
        
        page, url = await self.bot.utils.bs_from_url(self.bot,
                url[0], return_url=True)
        await self.parse_wiki_page(page, url)

    async def parse_wiki_page(self, page, url):
        """Parse a beautifulsoup object and URL object in to an embed"""
        tables = page.findAll('table')
        for table in tables:
            table.extract()
        if url.find('#') != -1:
            anchor = url.split('#')[1]
            page = str(page.find(id=anchor).findNext('p'))
        else:
            page = page.findAll('p')
            for pg in page:
                if str(pg)[0:9] == '<p><span ':
                    continue
                elif self.bot.utils.remove_html_tags(str(pg)).strip() == '':
                    continue
                elif pg.get_text().strip() == "":
                    continue
                else:
                    page = pg.extract()
                    break
        text = html2text.html2text(str(pg), bodywidth=5000).strip()
        text = text.replace('](/wiki', '](https://wikipedia.org/wiki')
        if text.rfind(".") != -1:
            text = text[0:text.rfind(".") + 1]
        try:
            embed_url = url.replace("(", "\\(").replace(")","\\)")
            embed_url = embed_url.replace("_","\\_")
            text = re.sub(r"\*\*(.+?)\*\*", 
                    f'**[\g<1>]({embed_url})**', text, 1)
        except:
            pass
        text = re.sub(r'\[\d*?\]', '', text)
        
        e = discord.Embed(description=text)
        await ctx.send(embed=e)





def setup(bot):
    bot.add_cog(Internets(bot))

