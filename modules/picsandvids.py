import discord
from discord.ext import commands
import asyncio
import random
import re
from io import BytesIO

from urllib.parse import quote as uriquote


class Pics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='image', aliases=['pic', 'gif'])
    async def image(self, ctx, *, search: str):
        """Google Image Search and return the results in a switchable embed"""
        if ctx.invoked_with.lower() == "gif":
            search += " gif"

        url = 'https://www.googleapis.com/customsearch/v1'
        params = {'key': self.bot.config.gsearch2, 'cx': self.bot.config.gsearchcx,
                   'q': uriquote(search), 'searchType': 'image'}
        if not ctx.channel.is_nsfw():
            params['safe'] = "medium"
        
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
            subreddit = reddits[ctx.invoked_with.lower()]
        url = f"http://www.reddit.com/r/{subreddit}/.json"

        headers = {'User-agent': 'PalBot by /u/mrsix'}
        async with self.bot.session.get(url, headers=headers) as resp:
            data = await resp.json()
        if 'data' not in data or not data['data']['children']:
            await ctx.send(f"Failed to load pics for r/{subreddit}")
            return
        catlist = []
        for cat in data['data']['children']:
            url = cat['data']['url']
            if '.gifv' not in url and ('.jpg' in url or '.gif' in url or ".png" in url or ".jpeg" in url):
                if cat['data']['over_18'] and not ctx.channel.is_nsfw():
                    continue
                catlist.append(cat['data'])
        
        if catlist:
            pages = self.bot.utils.Paginator(ctx, catlist, self.reddit_pics_callback)
            await pages.paginate()
        else:
            await ctx.send(f"Couldn't find any suitable pics in r/{subreddit}")
    
    async def reddit_pics_callback(self, data, pg):
        url = "https://reddit.com" + data[pg]['permalink']
        e = discord.Embed(title=data[pg]['title'][:255], url=url)
        e.set_image(url=data[pg]['url'])
        e.set_footer(text=f"Result {pg+1} of {len(data)}")
        return None, e

        



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
                'hl' : 'en', 'id': yt_id,  'key': key, 'regionCode': 'US'}
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
        if likes and dislikes:
            rating = "{0:.1f}/10".format((likes / (likes + dislikes)) * 10)
        else:
            rating = "N/A"
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
        if 'contentRating' in ytjson['contentDetails'] and \
          ytjson['contentDetails']['contentRating']:
            print(ytjson['contentDetails'])
            out = "**NSFW** : "
            link = f"|| {link} ||"

        out += (f"{title} [{category}] :: Length: {duration} - Rating: {rating} - "
                f"{viewcount:,} views - {uploader} on {pubdate} - {link}")

        await ctx.send(out)

    REDDIT_URL = re.compile(r'v\.redd\.it|reddit\.com/r/')
    URL_REGEX = re.compile(r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>])*\))+(?:\(([^\s()<>])*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))")
    @commands.Cog.listener()
    async def on_message(self, message):
        match = self.REDDIT_URL.search(message.content)
        if not match:
            return
        # This is a reddit url... but now I ned *only* the URL...
        url = self.URL_REGEX.search(message.content).group(0)
        if not url:
            return
        headers = {'User-agent': 'PalBot by /u/mrsix'}
        if "v.redd.it" in url:
            if url.lower().endswith("dashplaylist.mpd"):
                url = url[:-16]
            async with self.bot.session.get(url, headers=headers) as resp:
                url = str(resp.url)

        url = url[:url.rfind("/")] + "/.json"
        async with self.bot.session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return
            try:
                data = await resp.json()
            except Exception as e:
                print("Redditvideo json error on", url, e)
            try:
                submission = data[0]['data']['children'][0]['data']
            except (KeyError, TypeError, IndexError):
                return

            try:
                media = submission['media']['reddit_video']
            except (KeyError, TypeError):
                try:
                    # maybe it's a cross post
                    crosspost = submission['crosspost_parent_list'][0]
                    media = crosspost['media']['reddit_video']
                except (KeyError, TypeError, IndexError):
                    # Not a reddit video.. don't care about it
                    return

            filename = submission.get('title', '')
            if not filename:
                filename = submission.get('name', 'redditvideo')
            filename += ".mp4"
        
            fallback_url = media.get('fallback_url')
            if not fallback_url:
                return
            
            
        async with message.channel.typing():
            pass

        filesize = message.guild.filesize_limit if message.guild else 8388608
        async with self.bot.session.get(fallback_url, headers=headers) as resp:
            if resp.status != 200:
                return
            
            ctx = await self.bot.get_context(message, cls=self.bot.utils.MoreContext)

            if int(resp.headers['Content-Length']) >= filesize:
                fs = int(resp.headers['Content-Length']) / 1024 / 1024
                return await ctx.send(f"Video is too big to be uploaded. ({fs:.1f}mb)")

            data = await resp.read()
            await ctx.send(file=discord.File(BytesIO(data), filename=filename))

            

def setup(bot):
    bot.add_cog(Pics(bot))
    bot.add_cog(Vids(bot))
