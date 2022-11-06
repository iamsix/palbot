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
             url = ["http://en.wikipedia.org/wiki/Special:Random"]
        else:
            url = await self.bot.utils.google_for_urls(self.bot,
                    f"site:wikipedia.org {term}",
                    url_regex="wikipedia.org/wiki")

        page, url = await self.bot.utils.bs_from_url(self.bot, url[0], return_url=True)
        e = await self.parse_wiki_page(page, url)
        await ctx.send(embed=e)

    async def parse_wiki_page(self, page, url):
        """Parse a beautifulsoup object and Yarl.URL object (from bs4) in to an embed"""
        pagetitle = page.title.get_text()
        image = page.find(property="og:image")
        #Get rid of all tables before searching, they will cause failure
        tables = page.findAll('table')
        for table in tables:
            table.extract()

        if str(url).find('#') != -1:
            anchor = url.split('#')[1]
            page = page.find(id=anchor).findNext('p')
        else:
            page = page.findAll('p')
            for pg in page:
                if str(pg)[0:9] == '<p><span ':
                    continue
                elif pg.get_text().strip() == "":
                    continue
                elif self.bot.utils.remove_html_tags(str(pg)).strip() == '':
                    continue
                else:
                    page = pg.extract()
                    break
        
        text = re.sub(r'\[\d*?\]', '', str(pg))
        text = html2text.html2text(text, bodywidth=5000).strip()
        text = text.replace('](/wiki', f'](https://{url.host}/wiki')
        e = discord.Embed()
        
        embed_url = str(url).replace("(", "\\(").replace(")","\\)").replace("_","\\_")
        embed_url = embed_url
        link_first = re.sub(r"\*\*(.+?)\*\*", r'**[\g<1>]' + f'({embed_url})**', text, 1)
        if link_first == text:
            e.title = pagetitle
            e.url = str(url)
        else:
            text = link_first

        if image:
            e.set_thumbnail(url=image.get("content"))
       
        # TODO some kind of proper pagination here...
        e.description=text[:2000]
        
        return e

        
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
        
        loc = ctx.author_info.location
        if loc:
            location = uriquote(loc.formatted_address)
            lat = loc.latitude
            lng = loc.longitude
        else:
            location, lat, lng = "", "", ""
        
        key = self.bot.config.wolframAPIkey

        url = "http://api.wolframalpha.com/v2/query"
        params = {"appid": key, "format": 'plaintext', 'output': 'json',
                  "input": query, 
                  "location": location, "latlong": f"{lat},{lng}"}
       
        # print(params)
        # Wolfram api can take a while sometimes....
        async with ctx.channel.typing():
            if ctx.invoked_with.lower() == "c":
                result = await self.get_wolfram(url, params)
            else:
                result = await self.get_wolfram(url, params, full=True)
            if result:
                await ctx.send(result)
            else:
                await ctx.send("Wolfram didn't understand that")

    async def get_wolfram(self, url, params, *, full=False):
        """The recursive method used to look up wolfram data or woflram related data"""
        async with self.bot.session.get(url, params=params) as resp:
            data = await resp.read()
            data = json.loads(data)
        
        if not data['queryresult']['success'] or len(data['queryresult']['pods']) < 2:
            #Possibly recursively use didyoumeans with a high level here...
            return
        
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



async def setup(bot):
    await bot.add_cog(Internets(bot))

