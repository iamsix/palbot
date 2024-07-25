import discord
from discord.ext import commands
import csv
from urllib.parse import quote as uriquote
import xml.dom.minidom
import base64


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
                    # print(resp.status, url)
                    return await self.follow_news(newurl)
                else:
                    return await self.decode_google_news_url(resp.url)
        except TimeoutError:
            return url

    async def fetch_decoded_batch_execute(self, id):
        s = (
            '[[["Fbv4je","[\\"garturlreq\\",[[\\"en-US\\",\\"US\\",[\\"FINANCE_TOP_INDICES\\",\\"WEB_TEST_1_0_0\\"],'
            'null,null,1,1,\\"US:en\\",null,180,null,null,null,null,null,0,null,null,[1608992183,723341000]],'
            '\\"en-US\\",\\"US\\",1,[2,3,4,8],1,0,\\"655000234\\",0,0,null,0],\\"' +
            id +
            '\\"]",null,"generic"]]]'
        )

        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "Referer": "https://news.google.com/"
        }

        async with self.bot.session.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
            headers=headers,
            data={"f.req": s}
            ) as response:

            if response.status != 200:
                raise Exception("Failed to fetch data from Google.")

            text = await response.read()
            text = text.decode()
            header = '[\\"garturlres\\",\\"'
            footer = '\\",'
            if header not in text:
                raise Exception(f"Header not found in response: {text}")
            start = text.split(header, 1)[1]
            if footer not in start:
                raise Exception("Footer not found in response.")
            url = start.split(footer, 1)[0]
            return url

    async def decode_google_news_url(self, url):
        # url = requests.utils.urlparse(source_url)
        path = url.path.split("/")
        if url.host == "news.google.com" and len(path) > 1 and path[-2] == "articles":
            base64_str = path[-1]
            decoded_bytes = base64.urlsafe_b64decode(base64_str + '==')
            decoded_str = decoded_bytes.decode('latin1')

            prefix = b'\x08\x13\x22'.decode('latin1')
            if decoded_str.startswith(prefix):
                decoded_str = decoded_str[len(prefix):]

            suffix = b'\xd2\x01\x00'.decode('latin1')
            if decoded_str.endswith(suffix):
                decoded_str = decoded_str[:-len(suffix)]

            bytes_array = bytearray(decoded_str, 'latin1')
            length = bytes_array[0]
            if length >= 0x80:
                decoded_str = decoded_str[2:length+1]
            else:
                decoded_str = decoded_str[1:length+1]

            if decoded_str.startswith("AU_yqL"):
                return await self.fetch_decoded_batch_execute(base64_str)

            return decoded_str
        else:
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
            output = output.format(row['politician'], round(float(row['approve_estimate']), 1),
                                   round(float(row['disapprove_estimate']), 1), row['end_date'], url)
            await ctx.send(output)
    

async def setup(bot):
    await bot.add_cog(News(bot))
