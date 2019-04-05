import re
import json


def get_imdb(self, e, urlposted=False):
    #reads title, rating, and movie description of movie titles
    searchterm = e.input
    if urlposted:
        url = searchterm
    else:
        url = self.tools['google_url']("site:imdb.com inurl:com/title " + searchterm, "imdb.com/title/tt\\d{7}/")

    if not url:
        pass
    elif url.find("imdb.com/title/tt") != -1:
        movietitle = ""
        rating = ""
        summary = ""
        imdbid = re.search("tt\\d{7}", url)
        imdburl = ('http://www.imdb.com/title/' + imdbid.group(0) + '/')
        page = self.tools["load_html_from_URL"](imdburl)

        data = json.loads(page.find('script', type='application/ld+json').text)
        
        movietitle = "{} ({})".format(data['name'], data['datePublished'][:4])

        rating = ""
        description = ""

        try:
            rating = " - Rating: {}".format(data['aggregateRating']['ratingValue'])
        except KeyError:
            pass
        try:
            summary = " - {}".format(data['description'])
        except KeyError:
            pass

        try:
            if isinstance(data['genre'], list):
                genre = " - {}".format(", ".join(data['genre']))
            else:
                genre = " - {}".format(data['genre'])
        except KeyError:
            genre = ""

        title = movietitle + rating + genre + summary
        if not urlposted:
            title = title + " [ %s ]" % url

        e.output = title

        return e
get_imdb.command = "!imdb"
get_imdb.helptext = "Usage: !imdb <movie title>\nExample: !imdb the matrix\nLooks up a given movie title on IMDB and shows the movie rating and a synopsis"
