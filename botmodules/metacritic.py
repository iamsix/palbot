import json

def get_metacritic(self, e):
    url = self.tools['google_url']("site:metacritic.com " + e.input, "www.metacritic.com/")
    page = self.tools["load_html_from_URL"](url)

    data = json.loads(page.find('script', type='application/ld+json').text)

    title = data['name']
    category = ""
    if data['@type'] == "VideoGame":
        category = data['gamePlatform']
    elif data['@type'] == "Movie":
        category = "Film"
        title += " ({})".format(data['datePublished'][-4:])


    rating = "Score: {} ({} reviews)".format(data['aggregateRating']['ratingValue'],
                                             data['aggregateRating']['ratingCount'])


    out = "{} ({}): {} - {} [ {} ]".format(title, category, rating, data['description'], url)
    e.output = out


    return e

get_metacritic.command = "!mc"


