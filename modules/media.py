import discord
from discord.ext import commands
from urllib.parse import quote as uriquote
from utils.paginator import Paginator
import json
import asyncio
                

class Media(commands.Cog):
    """Contains movie related internets things"""
    def __init__(self, bot):
        self.bot = bot
        self.lastresult = None


    rt_search_url = ("http://api.flixster.com/android/api/v14/movies.json"
                     "?cbr=1&filter={}")
    rt_movie_url = "http://api.flixster.com/android/api/v1/movies/{}.json"
   

    @commands.command(name='rt')
    async def rt(self, ctx, *, movie_name: str):
        """Searches Flixster for a movie's Rotten Tomatoes score and critics consensus if available"""
        url = self.rt_search_url.format(uriquote(movie_name))
        data = await self.json_from_flxurl(url)
        movielist = []
        for movie in data:
            movielist.append(movie['id'])
        pages = Paginator(ctx, movielist, self.rt_output_callback)
        await pages.paginate()
        #await ctx.send(await self.parse_rt(movie))
        # Paginate here.


    async def rt_output_callback(self, data, pg_number):
        flxurl = self.rt_movie_url.format(data[pg_number])
        movie = await self.json_from_flxurl(flxurl)
        out = await self.parse_rt_embed(movie)
#        out.set_footer(text=f"Result {pg_number+1} of {len(data)}")
        return None, out

    async def json_from_flxurl(self, url):
        """used for any flixster url due to the special encoding"""
        async with self.bot.session.get(url) as resp:
            data = await resp.read()
            return json.loads(data.decode('windows-1252', 'replace'))

    async def parse_rt_embed(self, movie):
        title = f"{movie['title']} ({movie['theaterReleaseDate']['year']})"
        e = discord.Embed(title=title)
        try:
            for urls in movie['urls']:
                if urls['type'] == 'rottentomatoes':
                    e.url = urls['url'].replace('?lsrc=mobile','')
        except:
            pass
        
        try:
            concensus = movie['reviews']['rottenTomatoes']['consensus']
            e.description = self.bot.utils.remove_html_tags(concensus)
        except:
            pass

        try:
            tomato = (f"{movie['reviews']['rottenTomatoes']['rating']}%"
                    f" ({movie['reviews']['criticsNumReviews']} reviews)")
            e.add_field(name="Tomatometer", value=tomato)
        except:
            pass

        try:
            e.add_field(name="User Score",
                    value=movie['reviews']['flixster']['popcornScore'])
        except:
            pass

        try:
            e.set_thumbnail(url=movie['poster']['thumbnail'])
        except:
            pass

        return e
   

    async def parse_rt(self, movie):
        try:
            for urls in movie['urls']:
                if urls['type'] == 'rottentomatoes':
                    url = urls['url'].replace('?lsrc=mobile','')
        except:
            url = ""

        try:
            concensus = movie['reviews']['rottenTomatoes']['consensus']
            concensus = " - " + self.bot.utils.remove_html_tags(concensus)
        except:
            concensus = ""

        try:
            rt_rating = movie['reviews']['rottenTomatoes']['rating']
        except:
            rt_rating = "N/A"

        fmt = (f"{movie['title']} ({movie['theaterReleaseDate']['year']})"
               f" - Critics: {rt_rating}"
               f" - Users: {movie['reviews']['flixster']['popcornScore']}"
               f"{concensus} [ <{url}> ]")

        return fmt.format()



    @commands.command(name='imdb')
    async def imdb(self, ctx, *, movie_name: str):
        """Search for a movie or TV show on IMDB to return some info"""
        urls = await self.bot.utils.google_for_urls(self.bot, 
                "site:imdb.com inurl:com/title " + movie_name,
                url_regex="imdb.com/title/tt\\d{7}/")

        page = await self.bot.utils.bs_from_url(self.bot, urls[0])

        data = json.loads(page.find('script', 
            type='application/ld+json').text)

        movietitle = f"{data['name']} ({data['datePublished'][:4]})"
        
        e = discord.Embed(title=movietitle, url=urls[0])
        
        try:
            e.description = data['description']
        except KeyError:
            pass

        try:
            e.add_field(name="Rating", 
                    value=f"{data['aggregateRating']['ratingValue']}")
        except KeyError:
            pass

        try:
            if isinstance(data['genre'], list):
                e.add_field(name="Genres", value=", ".join(data['genre']))
            else:
                e.add_field(name="Genre", value=data['genre'])
        except KeyError:
            pass

        try:
            thumb = data['image'].replace(".jpg", "_UX128_.jpg")
            e.set_thumbnail(url=thumb)
        except KeyError:
            pass

        await ctx.send(embed=e)

def setup(bot):
    bot.add_cog(Media(bot))
