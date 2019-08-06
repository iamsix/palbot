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


    async def rt_output_callback(self, movieid):
        flxurl = self.rt_movie_url.format(movieid)
        movie = await self.json_from_flxurl(flxurl)
        out = await self.parse_rt(movie)
        return out, None

    async def json_from_flxurl(self, url):
        """used for any flixster url due to the special encoding"""
        async with self.bot.session.get(url) as resp:
            data = await resp.read()
            return json.loads(data.decode('windows-1252', 'replace'))

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
        # need a working google_for_url and bs_from_url here
        pass

def setup(bot):
    bot.add_cog(Media(bot))
