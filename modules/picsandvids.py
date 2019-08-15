import discord
from discord.ext import commands
import asyncio
import random

from urllib.parse import quote as uriquote


class Pics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='image', aliases=['pic', 'gif'])
    async def image(self, ctx, *, search: str):
        """Google Image Search and return the results in a switchable embed"""
        if ctx.invoked_with == "gif":
            search += " gif"
        search = uriquote(search)
        url = 'https://www.googleapis.com/customsearch/v1?key={}&cx={}&q={}&searchType=image'
        url = url.format(self.bot.config.gsearch2, self.bot.config.gsearchcx, search)
        if not ctx.channel.is_nsfw():
             url += "&safe=medium"
        
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            if 'items' not in data:
                await ctx.send(f"There are no images of `{search}` on Google Image Search")
                return

            data = data['items']
            pages = self.bot.utils.Paginator(ctx, data, self.image_callback)
            await pages.paginate()

    async def image_callback(self, data, pg):
        title = f"{pg + 1}. {data[pg]['title']}"
        e = discord.Embed(title=title, url=data[pg]['image']['contextLink'])
        e.set_image(url=data[pg]['link'])
        return None, e


    @commands.command(name='rpics', aliases=['cats', 'dogs', 'birds', 'sloths', 'rats'])
    async def reddit_pics(self, ctx, *, subreddit: str = ""):
        headers = {'User-agent': 'PalBot by /u/mrsix'}
        reddits = {'rpics': 'pics',
                    'cats': 'catpictures+cats',
                    'dogs': 'dogpictures+dogs',
                    'birds': 'birdpics',
                    'sloths': 'sloths',
                    'rats': 'rats'}
        if not subreddit:
            subreddit = reddits[ctx.invoked_with]
        url = f"http://www.reddit.com/r/{subreddit}/.json"

        async with self.bot.session.get(url) as resp:
            data = await resp.json()

        catlist = []
        for cat in data['data']['children']:
            if 'jpg' in cat['data']['url'] or 'imgur.com' in cat['data']['url'] or 'gfycat.com' in cat['data']['url']:
                pic_title = cat['data']['title']
                pic_title = pic_title.replace('\n', '')
                if cat['data']['over_18']:
                    pic_title = "\002NSFW\002 " + pic_title 
                catlist.append(f'<{cat["data"]["url"]}> - {pic_title}')
        
        cats = random.sample(catlist, 2)
        await ctx.send(" :: ".join(cats))

        



class Vids(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='yt')
    async def youtube(self, ctx, *, search: str):
        pass
        #When porting use the real youtube search probably?

def setup(bot):
    bot.add_cog(Pics(bot))