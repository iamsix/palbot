import discord
from discord.ext import commands
import csv
from urllib.parse import quote as uriquote
import json

import xml.dom.minidom
import base64
from yarl import URL

class News(commands.Cog):
    """Contains news and other current event functions"""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='news')
    async def bing_news(self, ctx, *, query: str = "cats"):
        url = f"https://www.bing.com/news/search?q={query}&format=rss"
        async with self.bot.session.get(url) as resp:
            data = await resp.read()
            dom = xml.dom.minidom.parseString(data)
            newest_news = dom.getElementsByTagName('item')[0]
            title = newest_news.getElementsByTagName('title')[0].childNodes[0].data.strip()
            link = newest_news.getElementsByTagName('link')[0].childNodes[0].data
            desc = newest_news.getElementsByTagName('description')[0].childNodes[0].data
            link = URL(link)
            url = URL(link.query['url'])
            #if url.host.lower() == "msn.com" or url.host.lower() == "www.msn.com":
            e = discord.Embed(title=title, url=url, description=desc)
            try:
                thurl = newest_news.getElementsByTagName('News:Image')[0].childNodes[0].data
                if "http" in thurl:
                    e.set_thumbnail(url=thurl)
            except:
                pass
            await ctx.send(embed=e)
            #else:
            #    await ctx.send(f'{title}\n{url}')



    @commands.command(name='gnews')
    async def google_news(self, ctx, *, query: str = ""):
        """Search for a story on google news - returns the headline and a link"""
        if not query:
            url = "https://news.google.com/news/rss/?hl=en"
        else:
            url = "https://news.google.com/news/rss/search/section/q/{0}/{0}?hl=en".format(uriquote(query))

        async with self.bot.session.get(url) as resp:
            data = await resp.read()
            dom = xml.dom.minidom.parseString(data)
            newest_news = dom.getElementsByTagName('item')[0]
            title = newest_news.getElementsByTagName('title')[0].childNodes[0].data.strip()
            link = newest_news.getElementsByTagName('link')[0].childNodes[0].data
            link = await self.follow_news(link)
            await ctx.send(f'{title} [ {link} ]')


    async def follow_news(self, url):
        headers = {"User-Agent": "Wget/1.21.2"}
        # Have to manually follow the redirects to account for timeouts
        try:
            async with self.bot.session.get(url, headers=headers, timeout=3, allow_redirects=False) as resp:
                if resp.status == 302:
                    newurl = resp.headers['Location']
                    # print(resp.status, url)
                    return await self.follow_news(newurl)
                else:
                    return await self.decode_single_url(resp.url)
        except TimeoutError:
            return url

    async def get_decoding_params(self, url):
        soup = await self.bot.utils.bs_from_url(self.bot, url)
        div = soup.select_one("c-wiz > div")
        gn_art_id = url.path.split("/")[-1]
        return {
            "signature": div.get("data-n-a-sg"),
            "timestamp": div.get("data-n-a-ts"),
            "gn_art_id": gn_art_id,
        }


    async def decode_urls(self, articles):
        articles_reqs = [
            [
                "Fbv4je",
                f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{art["gn_art_id"]}",{art["timestamp"]},"{art["signature"]}"]',
            ]
            for art in articles
        ]
        payload = f"f.req={uriquote(json.dumps([articles_reqs]))}"
        headers = {"content-type": "application/x-www-form-urlencoded;charset=UTF-8"}
        async with self.bot.session.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers=headers,
            data=payload) as response:
            
            response = await response.read()
            response = response.decode()
            return [json.loads(res[2])[1] for res in json.loads(response.split("\n\n")[1])[:-2]]


    async def decode_single_url(self, url):
        articles_params = [await self.get_decoding_params(url)]
        decoded_urls = await self.decode_urls(articles_params)
        return decoded_urls[0]

    @commands.command(name='approval')
    async def get_presidential_approval(self, ctx):
        """
        Gets presidential approval ratings from fivethirtyeight
        """
        data_url = "https://projects.fivethirtyeight.com/polls/approval/donald-trump/2/polling-average.json"
        url = 'https://projects.fivethirtyeight.com/polls/approval/donald-trump/'
        async with self.bot.session.get(data_url) as resp:
            data = await resp.json()
            # Only grab the top 3 lines from the CSV including the header


            output = "President: Trump 2 - {}: {:2.1f}% {}: {:2.1f}% Date: {} [ <{}> ]"
            output = output.format(data[0]['candidate'], data[0]['pct_estimate'],  
                                   data[1]['candidate'], data[1]['pct_estimate'],
                                   data[0]['date'], url)
            await ctx.send(output)
    

async def setup(bot):
    await bot.add_cog(News(bot))
