import discord
from discord.ext import commands
import csv
from urllib.parse import quote as uriquote
import xml.dom.minidom


class News(commands.Cog):
    """Contains news and other current event functions"""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='news')
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
                    #print(resp.status, url)
                    return await self.follow_news(newurl)
                else:
                    return resp.url
        except TimeoutError:
            return url

    @commands.command(name='approval')
    async def get_presidential_approval(self, ctx):
        """
        Gets presidential approval ratings from fivethirtyeight
        """
        data_url = "https://projects.fivethirtyeight.com/biden-approval-data/approval_topline.csv"
        url = 'https://projects.fivethirtyeight.com/biden-approval-rating/'
        async with self.bot.session.get(data_url) as resp:
            data = await resp.read()

            # Only grab the top 3 lines from the CSV including the header
            data = data.decode('utf-8').splitlines()[0:4] 
            reader = csv.DictReader(data)

            for row in reader:
                if row['subgroup'] == "All polls":
                    break

            output = "President: {} Approval: {}% Disapproval: {}% Date: {} [ <{}> ]"
            output = output.format(row['president'], round(float(row['approve_estimate']), 1),
                                   round(float(row['disapprove_estimate']), 1), row['modeldate'], url)
            await ctx.send(output)
    

async def setup(bot):
    await bot.add_cog(News(bot))
