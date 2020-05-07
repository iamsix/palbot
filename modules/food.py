import discord
from discord.ext import commands

import re
from urllib.parse import quote as uriquote
import json


class BeerCals:
    avg_fg = 1.012
    avg_beer_size_oz = 12
    avg_beer_size_ml = 330
    
    def __init__(self, abv, oz=None, ml=None):
        self.abv = abv
        self.oz = oz
        self.ml = ml

    def solve(self):
        if self.abv and self.oz:
            return(self.abv_oz_nofg_to_cals(self.abv, self.oz))
        elif self.abv and self.ml:
            return(self.abv_ml_nofg_to_cals(self.abv, self.ml))
        elif self.abv:
            return(self.abv_oz_nofg_to_cals(self.abv, self.avg_beer_size_oz))
        else:
            return ''
    
    def oz_to_ml(self,oz):
        return float(oz) * 29.574

    def ml_to_oz(self,ml):
        return float(ml) / 29.574

    def plato_to_sg(self, plato): #Plato to specific gravity
        return plato / (258.6 - (( plato / 258.2) * 227.1)) + 1

    def sg_to_plato(self, sg):
        return -676.67+1286.4*sg-800.47*(sg**2)+190.74*(sg**3)

    def og_and_fg_to_abv(self, og,fg): #original gravity and final gravity to ABV
        og = float(og)
        fg = float(fg)
        #return -17.1225210+146.6266588*og-130.2323766*fg
        return (1.05/0.70)*((og-fg)/fg)*100



    def og_and_abv_to_fg(self, og, abv): #convert from original gravity and ABV% to final gravity
        return og/((abv/150)+1)

    def abv_and_fg_to_sg(self, abv, fg):
        return (1+(abv/150))*fg

    def abv_and_ml_to_cals(self, abv, ml): #calorie count based on alcohol content only
        return float(ml)*(float(abv)/100)*7

    def fg_and_ml_to_cals(self, fg, ml): #calorie count based on residual sugars
        return float(ml)*(self.sg_to_plato(fg)/100)*3

    def og_abv_ml_to_cals(self, og, abv, ml):
        return int(round((self.abv_and_ml_to_cals(abv, ml) + (self.fg_and_ml_to_cals(self.og_and_abv_to_fg(og, abv), ml))),0))

    def og_abv_oz_to_cals(self, og, abv, oz):
        return self.og_abv_ml_to_cals(og, abv, self.oz_to_ml(oz))

    def abv_ml_nofg_to_cals(self, abv, ml): #Broad estimate based on just ABV and a typical FG of 1.012
        fg = self.avg_fg
        return int(round(self.abv_and_ml_to_cals(abv, ml) + self.fg_and_ml_to_cals(fg, ml),0))

    def abv_oz_nofg_to_cals(self, abv, oz): #Broad estimate again
        fg = self.avg_fg
        return int(round(self.abv_and_ml_to_cals(abv,  self.oz_to_ml(oz)) + self.fg_and_ml_to_cals(fg, self.oz_to_ml(oz)),0))

    def tokenize (self, calc_string):
        return re.split(r'\s', calc_string)


class Food(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='ba')
    async def advocate_beer(self, ctx, *, beer: str):
        """Search for a beeradvocate page"""
        url = await self.bot.utils.google_for_urls(self.bot, 
                                                "site:beeradvocate.com " + beer, 
                                                url_regex="/beer/profile/[0-9]*?/[0-9]+")
        #url = "http://beeradvocate.com/beer/profile/306/1212/"
        beerpage = await self.bot.utils.bs_from_url(self.bot, url[0])
        # due to scraping changes etc I've given up on updating this and am just returning the meta props
        out = beerpage.find(property="og:description").get("content") + f" [ <{url[0]}> ]"

        await ctx.send(out)


    @commands.command(name='beer')
    async def untappd_beer_search(self, ctx, *, beername: str):
        """Search Untappd for a beer to return ratings, alcohol, etc"""
        clientid = self.bot.config.untappd_clientid
        clientsecret = self.bot.config.untappd_clientsecret
        top_rating = 4.7        

        url = "https://api.untappd.com/v4/search/beer"
        params = {'client_id': clientid, 'client_secret': clientsecret,
                  'q': uriquote(beername)}

        async with self.bot.session.get(url, params=params) as resp:
            if resp.status != 200:
                return
            response = await resp.json()
            if not response['response']['beers']['items']:
                await ctx.send(f"Couldn't find a beer named `{beername}` on Untappd")
                return
                
        beerid = response['response']['beers']['items'][0]['beer']['bid']
        
        params = {'client_id': clientid, 'client_secret': clientsecret}
        url = f"https://api.untappd.com/v4/beer/info/{beerid}?"
        async with self.bot.session.get(url, params=params) as resp:
            response = await resp.json()
            response = response['response']['beer']

        beer_name = response['beer_name']
        beer_abv = response['beer_abv']
        #beer_ibu = response['beer_ibu']
        beer_style = response['beer_style']

       
        beer_url = f"https://untappd.com/b/{response['beer_slug']}/{beerid}"
                
        rating = int(round((float(response['rating_score'])/top_rating)*100, 0))
        rating_count = int(response['rating_count'])

        if rating >=95:
            rating_word = "world-class"
        elif 90 <= rating <= 94:
            rating_word = "outstanding"
        elif 85 <= rating <= 89:
            rating_word = "very good"
        elif 80 <= rating <= 84:
            rating_word = "good"
        elif 70 <= rating <=79:
            rating_word = "okay"
        elif 60 <= rating <=69:
            rating_word = "poor"
        elif rating < 60:
            rating_word = "awful"

        cals = BeerCals(beer_abv).solve()

        e = discord.Embed(title=f"{beer_name} - {beer_style}", url=beer_url)
        e.add_field(name="Grade", value=f"{rating} - {rating_word} ({rating_count:,} ratings)", inline=False)
        
        if cals:
            beer_abv = f"{beer_abv}% - Est. Calories (12oz): {cals}"

        e.add_field(name="ABV", value=beer_abv, inline=False)
        if 'beer_label' in response:
            e.set_thumbnail(url=response['beer_label'])

        await ctx.send(embed=e)

    @commands.command()
    async def drink(self, ctx, *, drink: str = ''):
        """Search for a cocktail recipe"""
        if drink:
            url = f"http://www.thecocktaildb.com/api/json/v1/1/search.php?s={uriquote(drink)}"
        else:
            url = "http://www.thecocktaildb.com/api/json/v1/1/random.php"
        
        async with self.bot.session.get(url) as resp:
            response = await resp.json()
        drink = response["drinks"][0]

        #this API is a bit odd that it doesn't make these a list to iterate them
        #it just lists 1 through 15 each time...
        ingredients = ""
        for ingr in range(1,15):
            if drink["strIngredient{}".format(ingr)]:
                ingredient = drink["strIngredient{}".format(ingr)]
                ingredient = ingredient.replace("\n", "").strip()
                measure = drink["strMeasure{}".format(ingr)]
                measure = measure.replace("\n", "").strip()
                ingredients += "{} {}\n".format(measure, ingredient)

        output = "**{}** - {} - {}\n{}Instructions: {}"

        output = output.format(drink["strDrink"], drink["strCategory"], 
                                drink["strGlass"],
                                ingredients,
                                drink["strInstructions"])
        await ctx.send(output)

    @commands.command()
    async def spirits(self, ctx, *, spirit: str):
        """Search Distiller.com for a <spirit> and return some information about it"""
        url = await self.bot.utils.google_for_urls(self.bot, 
                                            "site:distiller.com {}".format(spirit),
                                            url_regex="distiller.com/spirits/")
        if not url:
            await ctx.send(f"Unabled to find a spirit named `{spirit}` on Distiller")
            return

        jsurl = url[0].replace('r.com/', 'r.com/api/')
        headers = {'User-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0',
                   'X-DISTILLER-DEVELOPER-TOKEN': self.bot.config.distillertoken}
                   
        async with self.bot.session.get(jsurl, headers=headers) as resp:
            data = await resp.json()
            data = data['spirit']
        
        style = data['spirit_family']['name']
        name = data['name']
        exp_rate = data['expert_rating']
        pub_rate = data['average_rating']
        num_raters = data['total_num_of_ratings']
        abv = data['abv']
        description = data['description']

        # TODO Paginate this?
        e = discord.Embed(title=f"{style}: {name}", url=url[0])
        e.add_field(name="Rating", value=f"{exp_rate} / Users: {pub_rate} ({num_raters} ratings)")
        e.add_field(name="ABV", value=abv)
        e.set_footer(text=description)

        if 'thumbnail' in data['image_urls']:
            e.set_thumbnail(url=data['image_urls']['thumbnail'])

        await ctx.send(embed=e)


    CUISINE = {"african": 1,"indian": 2,"french": 3,"british": 4,"european": 5,
            "italian": 6, "australian": 7,"jewish": 8,"asian": 9,"mexican": 10,
            "latin american": 11, "thai": 12, "chinese": 13,"irish": 14,
            "american": 15,"spanish": 16,"turkish": 17, "vietnamese": 18,
            "greek": 19,"moroccan": 20,"caribbean": 21,"mediterranean": 22,
            "japanese": 23}


    INGREDIENTS = {"dairy": 2, "seafood": 7, "pasta": 8, "vegetable": 9, "egg": 11,
                "fish": 13, "lamb": 36, "pork": 37, "duck": 39, "chicken": 42,
                "beef": 59, "turkey": 98}

    @commands.command(name='wfd')
    async def get_recipe(self, ctx, inpt: str = ""):
        """Get a random recipe from reciperoulette.tv"""

        url = "http://www.reciperoulette.tv/getRecipeInfo"

        inpt = inpt.lower().strip()
        ingdt = ""
        cusine = ""
        
        if inpt in self.CUISINE:
            cusine = self.CUISINE[inpt]
        if inpt in self.INGREDIENTS:
            ingdt = self.INGREDIENTS[inpt]
        post = {'ingdt': ingdt, 'diet': '', 'cusine': cusine}

        async with self.bot.session.post(url, data=post) as resp:
            data = await resp.read()
            data = json.loads(data)

        out = "{} - {} : <http://www.reciperoulette.tv/#{}>"
        out = out.format(data['name'], data['description'], data['id'])
        
        await ctx.send(out)
    

def setup(bot):
    bot.add_cog(Food(bot))

