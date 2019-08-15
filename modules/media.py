import discord
from discord.ext import commands
from urllib.parse import quote as uriquote
from utils.paginator import Paginator
import json
import asyncio
import xml.dom.minidom


class Media(commands.Cog):
    """Contains movie related internets things"""
    def __init__(self, bot):
        self.bot = bot


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

        movie_model = {
            'title': '',
            'urls': [],
            'theaterReleaseDate':{
                'year': ''
                },
            'reviews': {
                'rottenTomatoes': {
                    'rating': '',
                    'consensus': ''
                },
                'criticsNumReviews': '',
                'flixster': {
                    'popcornScore': ''
                }
            },
            'poster': {
                'thumbnail': ''
            }
        }

        self.bot.utils.dict_merge(movie_model, movie)

        title = f"{movie_model['title']} ({movie_model['theaterReleaseDate']['year']})"
        description = self.bot.utils.remove_html_tags(movie_model['reviews']['rottenTomatoes']['consensus'])

        e = discord.Embed(title=title, description=description)

        for urls in movie_model['urls']:
            if urls.get('type', '') == 'rottentomatoes':
                e.url = urls['url'].replace('?lsrc=mobile','')
        e.set_thumbnail(url=movie_model['poster']['thumbnail'])

        tomato_rating = movie_model['reviews']['rottenTomatoes']['rating']
        num_reviews = movie_model['reviews']['criticsNumReviews']

        tomato = "{rating}{reviews}".format(
            rating = f"{tomato_rating}%" if tomato_rating else '',
            reviews = f" ({num_reviews} reviews)" if num_reviews else '')

        embed_fields = {"Tomatometer": tomato,
                        "User Score": movie_model['reviews']['flixster']['popcornScore']}

        for k,v in embed_fields.items():
            if str(v).strip():
                e.add_field(name=k, value=str(v))
        return e



    @commands.command(name='imdb')
    async def imdb(self, ctx, *, movie_name: str):
        """Search for a movie or TV show on IMDB to return some info"""

        imdb_m = {'name': '',
                  'datePublished': '',
                  'description': '',
                  'aggregateRating': {
                      'ratingValue': ''
                      },
                  'genre': '',
                  'image': ''
        }


        urls = await self.bot.utils.google_for_urls(self.bot,
                "site:imdb.com inurl:com/title " + movie_name,
                url_regex="imdb.com/title/tt\\d{7}/")

        page = await self.bot.utils.bs_from_url(self.bot, urls[0])

        data = json.loads(page.find('script', type='application/ld+json').text)

        self.bot.utils.dict_merge(imdb_m, data)

        movie_title = f"{imdb_m['name']} ({imdb_m['datePublished'][:4]})"
        desc = imdb_m['description']

        e = discord.Embed(title=movie_title, description=desc, url=urls[0])

        rating = imdb_m['aggregateRating']['ratingValue']
        if isinstance(imdb_m['genre'], list):
            genre = ", ".join(imdb_m['genre'])
        else:
            genre = imdb_m['genre']

        thumb = imdb_m['image'].replace(".jpg", "_UX128_.jpg")
        e.set_thumbnail(url=thumb)

        embed_fields = {"Rating": rating, "Genre": genre}
        for k,v in embed_fields.items():
            if str(v).strip():
                e.add_field(name=k, value=str(v))

        await ctx.send(embed=e)

    @commands.command(name='mc')
    async def metacritic(self, ctx, *, title: str):
        """Search for a metacrtic entry to get its MC rating and info"""

        mc_model = {'name': '',
                    '@type': '',
                    'gamePlatform': '',
                    'datePublished': '',
                    'description': '',
                    'aggregateRating': {
                        'ratingValue': '',
                        'ratingCount': '',
                    },
                    'genre': [],
                    'image': ''
        }

        urls = await self.bot.utils.google_for_urls(self.bot,
                "site:metacritic.com " + title,
                url_regex="www.metacritic.com/")

        page = await self.bot.utils.bs_from_url(self.bot, urls[0])

        data = json.loads(page.find('script',
            type='application/ld+json').text)

        self.bot.utils.dict_merge(mc_model, data)

        title = mc_model['name']
        category = mc_model['@type']
        if mc_model['@type'] == "VideoGame":
            category = mc_model['gamePlatform']
        elif mc_model['@type'] == "Movie":
            category = "Film"
            title += " ({})".format(mc_model['datePublished'][-4:])

        e = discord.Embed(title=f"{title} ({category})", url=urls[0])
        e.description = mc_model['description']
        e.set_thumbnail(url=mc_model['image'])

        mc_rating = mc_model['aggregateRating']['ratingValue']
        mc_rating_count = mc_model['aggregateRating']['ratingCount']
        rating = "{}{}".format(mc_rating, f' ({mc_rating_count} reviews)' if mc_rating_count else '')

        embed_fields = {"MC Rating": rating, "Genres": ", ".join(mc_model['genre'])}

        for k,v in embed_fields.items():
            if str(v).strip():
                e.add_field(name=k, value=str(v))

        await ctx.send(embed=e)

    @commands.command(name='gr')
    async def get_goodreads_book_rating(self, ctx, *, book: str = ""):
        key = self.bot.config.goodreadskey
        
        url = f"https://www.goodreads.com/search.xml?key={key}&q={uriquote(book)}"

        async with self.bot.session.get(url) as resp:
            response = await resp.read()
            dom = xml.dom.minidom.parseString(response)

        title = dom.getElementsByTagName("title")[0].firstChild.nodeValue
        name = dom.getElementsByTagName("name")[0].firstChild.nodeValue
        avgrating = dom.getElementsByTagName("average_rating")[0].firstChild.nodeValue
        ratingscount = dom.getElementsByTagName("ratings_count")[0].firstChild.nodeValue
    
        #apparently some books don't have a year
        try:
            pubyear = dom.getElementsByTagName("original_publication_year")[0].firstChild.nodeValue
            pubyear = f" ({pubyear})"
        except ValueError:
            pubyear = ""
        
        bookid = dom.getElementsByTagName("best_book")[0].getElementsByTagName("id")[0].firstChild.nodeValue
        bookurl = f"https://www.goodreads.com/book/show/{bookid}"
        
        output = (f"{title} by {name}{pubyear} | Avg rating: {avgrating} ({ratingscount} ratings) | "
                  f"{bookdesc} [ {bookurl} ]")
        await ctx.send(output)


def setup(bot):
    bot.add_cog(Media(bot))
