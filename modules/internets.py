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
        e = await self.parse_wiki_page(page, url)
        await ctx.send(embed=e)

    async def parse_wiki_page(self, page, url):
        """Parse a beautifulsoup object and URL object in to an embed"""
        tables = page.findAll('table')
        for table in tables:
            table.extract()
        if url.find('#') != -1:
            anchor = url.split('#')[1]
            page = page.find(id=anchor).findNext('p')
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
        
        return discord.Embed(description=text)
        
    @commands.command()
    async def gwiki(self, ctx, *, searchterm: str):
        """Attempts to use the google search snippet to find specific sections on wikipedia (it's not very good at it)"""
        search = f"site: wikipedia.org {uriquote(searchterm)}"
        results = await self.bot.utils.google_for_urls(self.bot, 
                                                        search, 
                                                        return_full_data=True)

        description = results[0]['snippet'].replace('\n', '')
        description += f' [ <{results[0]["link"]}> ]'
        await ctx.send(description)


    @commands.command(aliases=['c'])
    async def wolfram(self, ctx, *, query: str):
        """Query wolfram alpha and return the output"""
        location, lat, lng = "", "", ""
        if ctx.author_info.location:
            location = uriquote(ctx.author_info.location.formatted_address)
            lat = ctx.author_info.location.latitude
            lng = ctx.author_info.location.longitude
        key = self.bot.config.wolframAPIkey

        url = (f"http://api.wolframalpha.com/v2/query?appid={key}"
                "&format=plaintext&output=json&input={}"
               f"&location={location}&latlong={lat},{lng}")
        if ctx.invoked_with.lower() == "c":
            result = await self.get_wolfram(url, query)
        else:
            result = await self.get_wolfram(url, query, full=True)
        if result:
            await ctx.send(result)

    async def get_wolfram(self, url, query, *, full=False):
        """The recursive method used to look up wolfram data or woflram related data"""
        furl = url.format(uriquote(query))
        async with self.bot.session.get(furl) as resp:
            data = await resp.read()
            data = json.loads(data)
        
        if not data['queryresult']['success'] or len(data['queryresult']['pods']) < 2:
            #Possibly recursively use didyoumeans with a high level here...
            return
        
        #ls = data['queryresult']['pods'][0]['subpods'][0]['plaintext']
        #rs = data['queryresult']['pods'][1]['subpods'][0]['plaintext']
        pods = []
        for pod in data['queryresult']['pods']:
            if pod['subpods'][0]['plaintext']:
                pods.append(f"{pod['title']}: {pod['subpods'][0]['plaintext']}")
        ls = pods.pop(0).replace("\n", " :: ")
        if full: 
            rs = "\n".join(pods)
            out = f"{ls}: \n```{rs}\n```"
            if len(out) > 2000:
                #could use text paginator here but....
                out = out[:1990] + "\n```"
        else:
            rs = pods[0].replace("\n", " :: ")
            out = f"{ls} :: {rs}"
        return out






def setup(bot):
    bot.add_cog(Internets(bot))

