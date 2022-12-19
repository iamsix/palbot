import discord
from discord.ext import commands
from urllib.parse import quote as uriquote
from utils.paginator import Paginator
import json
import asyncio
import xml.dom.minidom
import html
import re


class Media(commands.Cog):
    """Contains movie related internets things"""
    def __init__(self, bot):
        self.bot = bot


    @commands.command(name='rt')
    async def rt(self, ctx, *, movie_name: str):
        """Searches Flixster for a movie's Rotten Tomatoes score and critics consensus if available"""
        # this uses a private API so the URL isn't published.
        # see a previous version of this file for an older semi-public API
        # however it seems to fail on newer movies unfortunately
        url = self.bot.config.rt_url_1 + movie_name
        url += self.bot.config.rt_url_2
        headers = self.bot.config.rt_headers
        async with self.bot.session.get(url, headers=headers) as resp:
            data = await resp.json()
        movielist = data['data']['search']['movies']
        if not movielist:
            await ctx.send(f"Couldn't find a movie named `{movie_name}` on Flixster")
            return
        pages = Paginator(ctx, movielist, self.rt_output_callback)
        await pages.paginate()


    async def rt_output_callback(self, data, pg_number):
        movie = data[pg_number]
        out = await self.parse_rt_embed(movie)
        return None, out

    async def parse_rt_embed(self, movie):
        self.bot.logger.debug(movie)
        year = movie['releaseDate'] or ''
        title = f"{movie['name']} ({year[:4]})"
        e = discord.Embed(title=title)
        if movie['posterImage']:
            poster = movie['posterImage']['url']
            poster = poster[poster.rfind("https://"):]
            e.set_thumbnail(url=poster)
        
        e.url = f"https://www.rottentomatoes.com/m/{movie['emsId']}"

        if movie['tomatoRating']:
            description = movie['tomatoRating']['consensus'] or ''
            description = self.bot.utils.remove_html_tags(description)
            e.description = description

            tomato_rating = movie['tomatoRating']['tomatometer']
            num_reviews = movie['tomatoRating']['ratingCount']
        
            if "certifiedfresh" in movie['tomatoRating']['iconImage']['url']:
                icon = '<:rtcertified:623695619017539584> '
            elif tomato_rating and int(tomato_rating) >= 60:
                icon = '\N{TOMATO} '
            else:
                icon = '<:rtrotten:623695558141411329> '

            tomato = "{icon}{rating}{reviews}".format(icon=icon,
                rating = f"{tomato_rating}%" if tomato_rating else '',
                reviews = f" ({num_reviews} reviews)" if num_reviews else '')

            if 'userRating' in movie and movie['userRating']:
                user = movie['userRating'].get('dtlLikedScore', "")
            else:
                user = ""

            embed_fields = {"Tomatometer": tomato,
                            "User Score": user}

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
                url_regex="imdb.com/title/tt\\d+/")

        if not urls:
            await ctx.send(f"Couldn't find a movie named `{movie_name}` on IMDb")
            return

        imdbid = re.search(r"tt\d+", urls[0]).group(0)
        url = f"https://imdb.com/title/{imdbid}/"

        headers = {'User-Agent': "Mozilla/5.0 (X11; Linux x86_64; rv:91.0) Gecko/20100101 Firefox/91.0"}
        page = await self.bot.utils.bs_from_url(self.bot, url, headers=headers)
        data = json.loads(page.find('script', type='application/ld+json').string)

        self.bot.utils.dict_merge(imdb_m, data)

        movie_title = f"{imdb_m['name']} ({imdb_m['datePublished'][:4]})"
        movie_title = html.unescape(movie_title)
        desc = html.unescape(imdb_m['description'])

        e = discord.Embed(title=movie_title, description=desc, url=url)

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
                url_regex="metacritic.com/(tv|game|movie|music)")

        page = await self.bot.utils.bs_from_url(self.bot, urls[0])

        data = json.loads(page.find('script', type='application/ld+json').string)

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

    @commands.command(name='gr', aliases=['book'])
    async def get_goodreads_book_rating(self, ctx, *, book: str):
        """Find a <book> on goodreads.com and return some rating info and a link"""
        key = self.bot.config.goodreadskey
        
        url = f"https://www.goodreads.com/search.xml"
        params = {'key': key, 'q': book}

        async with self.bot.session.get(url, params=params) as resp:
            response = await resp.read()
            dom = xml.dom.minidom.parseString(response)

        title = dom.getElementsByTagName("title")[0].firstChild.nodeValue
        name = dom.getElementsByTagName("name")[0].firstChild.nodeValue
        avgrating = dom.getElementsByTagName("average_rating")[0].firstChild.nodeValue
        ratingscount = int(dom.getElementsByTagName("ratings_count")[0].firstChild.nodeValue)
    
        #apparently some books don't have a year
        try:
            pubyear = dom.getElementsByTagName("original_publication_year")[0].firstChild.nodeValue
            pubyear = f" ({pubyear})"
        except ValueError:
            pubyear = ""
        
        bookid = dom.getElementsByTagName("best_book")[0].getElementsByTagName("id")[0].firstChild.nodeValue
        bookurl = f"https://www.goodreads.com/book/show/{bookid}"
        
        output = f"{title} by {name}{pubyear} | Avg rating: {avgrating} ({ratingscount:,} ratings) | [ {bookurl} ]"
        await ctx.send(output)


async def setup(bot):
    await bot.add_cog(Media(bot))
