import discord
from discord.ext import commands

import re
from urllib.parse import quote as uriquote

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
        return re.split('\s', calc_string)


class Alcohol(commands.Cog):
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

        auth = f"client_id={clientid}&client_secret={clientsecret}"
        url = f"https://api.untappd.com/v4/search/beer?q={uriquote(beername)}&{auth}"

        async with self.bot.session.get(url) as resp:
            response = await resp.json()
                
        beerid = response['response']['beers']['items'][0]['beer']['bid']
        
        url = f"https://api.untappd.com/v4/beer/info/{beerid}?{auth}"
        async with self.bot.session.get(url) as resp:
            response = await resp.json()
            response = response['response']['beer']

        beer_name = response['beer_name']
        beer_abv = response['beer_abv']
        beer_ibu = response['beer_ibu']
        beer_style = response['beer_style']
        
        beer_url = f"https://untappd.com/b/{response['beer_slug']}/{beerid}"
                
        rating = int(round((float(response['rating_score'])/top_rating)*100, 0))
        rating_count = response['rating_count']

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

        if cals:
            cals = f" Est. calories (12oz): {cals}"

        out = (f"Beer: {beer_name} - Grade: {rating} [{rating_word}, {rating_count} ratings] "
               f"Style: {beer_style} ABV: {beer_abv}%{cals} [ <{beer_url}> ]")
        
        await ctx.send(out)

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
                                            "site:distiller.com {}".format(uriquote(spirit)),
                                            url_regex="distiller.com/spirits/")

        jsurl = url[0].replace('r.com/', 'r.com/api/')
        headers = {'User-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0',
                   'X-DISTILLER-DEVELOPER-TOKEN': self.bot.config.distillertoken}
                   
        async with self.bot.session.get(jsurl, headers=headers) as resp:
            data = await resp.json()
            print(data)
            data = data['spirit']
        
        stlye = data['spirit_family']['name']
        name = data['name']
        exp_rate = data['expert_rating']
        pub_rate = data['average_rating']
        num_raters = data['total_num_of_ratings']
        abv = data['abv']
        description = data['description']
        # I probably could have done this by passing *data to a format() instead...
        # TODO Paginate this?
        # TODO make a fancy embed
        
        out = (f"{stlye}: {name} - Expert rating: {exp_rate} - User rating: {pub_rate} "
              f"({num_raters} ratings) ABV: {abv} - {description} [ <{url[0]}> ]")

        await ctx.send(out)
        
    

def setup(bot):
    bot.add_cog(Alcohol(bot))

