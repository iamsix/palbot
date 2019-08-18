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
        if ctx.invoked_with.lower() == "gif":
            search += " gif"

        url = 'https://www.googleapis.com/customsearch/v1?'
        params = {'key': self.bot.config.gsearch2, 'cx': self.bot.config.gsearchcx,
                   'q': uriquote(search), 'searchType': 'image'}
        if not ctx.channel.is_nsfw():
             url += "&safe=medium"
        
        async with self.bot.session.get(url, params=params) as resp:
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
        """Search a subreddit for any image files and return 2 random ones"""

        reddits = {'rpics': 'pics',
                    'cats': 'catpictures+cats',
                    'dogs': 'dogpictures+dogs',
                    'birds': 'birdpics',
                    'sloths': 'sloths',
                    'rats': 'rats'}
        if not subreddit:
            subreddit = reddits[ctx.invoked_with]
        url = f"http://www.reddit.com/r/{subreddit}/.json"

        headers = {'User-agent': 'PalBot by /u/mrsix'}
        async with self.bot.session.get(url, headers=headers) as resp:
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

    #TODO : Reddit video (on_message)

    @commands.command(name='yt')
    async def youtube(self, ctx, *, search: str):
        """Search for a youtube video and return some info along with an embedded link"""
        key = self.bot.config.gsearch2
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {'part' : 'snippet', 'q': uriquote(search), 'type': 'video',
                  'maxResults': 1, 'key' : key}
        
        async with self.bot.session.get(url, params=params) as resp:
            data = await resp.json()
            if data['items']:
                yt_id = data['items'][0]['id']['videoId']
            else:
                await ctx.send(f"Unable to find a youtube video for `{search}`")
                return
        link = f"https://youtu.be/{yt_id}"


        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {'part': "snippet,contentDetails,statistics",
                  'hl' : 'en', 'id': yt_id,  'key': key}
        async with self.bot.session.get(url, params=params) as resp:
            ytjson = await resp.json()
            if ytjson['items']:
                ytjson = ytjson['items'][0]
            else:
                await ctx.send(f"Failed to load video info for `{link}`")
                return
            
        
        title = ytjson['snippet']['title']
        uploader = ytjson['snippet']['channelTitle']
        pubdate = ytjson['snippet']['publishedAt'][:10]
        likes = int(ytjson['statistics'].get('likeCount', 0))
        dislikes = int(ytjson['statistics'].get('dislikeCount', 0))
        rating = "{0:.1f}/10".format((likes / (likes + dislikes)) * 10)
        viewcount = int(ytjson['statistics']['viewCount'])

        duration = ytjson['contentDetails']['duration'][2:].lower()

        category = ""
        catid = ytjson['snippet']['categoryId']
        url = "https://www.googleapis.com/youtube/v3/videoCategories"
        params = {'part': 'snippet', 'id': catid, 'key': key}
        async with self.bot.session.get(url, params=params) as resp:
            catjson = await resp.json()
            category = catjson['items'][0]['snippet']['title']

        out = ""
        if 'contentRating' in ytjson['contentDetails']:
            out = "**NSFW** : "

        out += (f"{title} [{category}] :: Length: {duration} - Rating: {rating} - "
                f"{viewcount:,} views - {uploader} on {pubdate} - {link}")

        await ctx.send(out)

            


def setup(bot):
    bot.add_cog(Pics(bot))
    bot.add_cog(Vids(bot))