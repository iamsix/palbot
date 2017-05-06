import urllib.request
import urllib.parse
import json

def drinks(self, e):
    pass
    url = "http://www.thecocktaildb.com/api/json/v1/1/search.php?s={}"
    url = url.format(urllib.parse.quote(e.input))

    response = urllib.request.urlopen(url).read()
    response = json.loads(response.decode())

   # print(response)
    drink = response["drinks"][0]

    print(drink)

    #this API is a bit odd that it doesn't make these a list  to iterate them
    #it just lists 1 through 15 each time...
    ingredients = ""
    for ingr in range(1,15):
        if drink["strIngredient{}".format(ingr)]:
            ingredient = drink["strIngredient{}".format(ingr)]
            ingredient = ingredient.replace("\n", "").strip()
            measure = drink["strMeasure{}".format(ingr)]
            measure = measure.replace("\n", "").strip()
            ingredients += "{} {}\n".format(measure, ingredient)
    ingredients = ingredients[:-1]

    output = """**{}** - {} - {}
{}
Instructions: {}"""

    e.output = output.format(drink["strDrink"], drink["strCategory"], 
                             drink["strGlass"],
                             ingredients,
                             drink["strInstructions"])

drinks.command = "!drink"


class drinktest:
     pass

drinktest.input = "vodka martini"
drinktest.output = ""
drinks(None, drinktest)
print(drinktest.output)
