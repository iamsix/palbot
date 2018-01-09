import json
import urllib.request



CUISINE = {"african": 1,"indian": 2,"french": 3,"british": 4,"european": 5,
           "italian": 6, "australian": 7,"jewish": 8,"asian": 9,"mexican": 10,
           "latin american": 11, "thai": 12, "chinese": 13,"irish": 14,
           "american": 15,"spanish": 16,"turkish": 17, "vietnamese": 18,
           "greek": 19,"moroccan": 20,"caribbean": 21,"mediterranean": 22,
           "japanese": 23}


INGREDIENTS = {"dairy": 2, "seafood": 7, "pasta": 8, "vegetable": 9, "egg": 11,
               "fish": 13, "lamb": 36, "pork": 37, "duck": 39, "chicken": 42,
               "beef": 59, "turkey": 98}

def get_recipe(self, e):

    url = "http://www.reciperoulette.tv/getRecipeInfo"

    inpt = e.input.lower().strip()
    # for later use we may want to support some of this    
    ingdt = ""
    cusine = ""
    
    if inpt in CUISINE:
        cusine = CUISINE[inpt]
    
    if inpt in INGREDIENTS:
        ingdt = INGREDIENTS[inpt] 
    post = "ingdt={}&diet=&cusine={}".format(ingdt, cusine)

    req = urllib.request.Request(url, post.encode())
    data = urllib.request.urlopen(req).read().decode('utf-8')
    data = json.loads(data)

    out = "{} - {} : http://www.reciperoulette.tv/#{}"
    e.output = out.format(data['name'], data['description'], data['id'])
    return e

get_recipe.command = "!wfd"
#get_recipe(None, get_recipe)
#print(get_recipe.output)

