import urllib.request, urllib.parse, xml.dom.minidom, re

def get_goodreads_book_rating(self, e):
    
    # Read the API key from the main bot object. It loads the config for us.
    goodreadskey = self.botconfig["APIkeys"]["goodreadskey"]
    
    query = urllib.parse.urlencode({"key":goodreadskey, "q":e.input}) #Pass the command input directly into the URL query
    url = "https://www.goodreads.com/search.xml"

    #Load XML response and parse DOM in one shot
    dom = xml.dom.minidom.parse(urllib.request.urlopen("%s?%s" % (url,query)))

    # This finds the first `title` tag and gets its text value
    firsttitle = dom.getElementsByTagName("title")[0].firstChild.nodeValue

    # At this point `firsttitle` contains the title of the first book found by Goodreads
    
    # These all do the same as above, first name, first rating, etc
    name = dom.getElementsByTagName("name")[0].firstChild.nodeValue
    avgrating = dom.getElementsByTagName("average_rating")[0].firstChild.nodeValue
    ratingscount = dom.getElementsByTagName("ratings_count")[0].firstChild.nodeValue
 
    #apparently some books don't have a year
    try:
        pubyear = dom.getElementsByTagName("original_publication_year")[0].firstChild.nodeValue
    except:
        pubyear = ""
    #Find the first `best_book` tag and then inside of that get the first `id` tag's value
    bookid = dom.getElementsByTagName("best_book")[0].getElementsByTagName("id")[0].firstChild.nodeValue
 
    
    # Set the URL to the user friendly URL you would load in your web browser
    bookurl = "https://www.goodreads.com/book/show/%s" % bookid
    bookpage = self.tools['load_html_from_URL'](bookurl)

    try:   
        bookdesc = bookpage.find("meta", property="og:description")['content'] 
    except:
        bookdesc = ""
    
    # Use the bot function to Google shorten the URL
    bookurl = self.tools['shorten_url'](bookurl)
    
    # %s gets substituted with variables in % (foo, bar)
    output = "%s by %s (%s) | Avg rating: %s (%s ratings) | %s [ %s ]" % (firsttitle, name, pubyear, avgrating, ratingscount, bookdesc, bookurl)    
    e.output = output

    return e
        


get_goodreads_book_rating.command = "!gr"
get_goodreads_book_rating.helptext = "Usage: !gr <book title> Retrieves book ratings from Goodreads."

# HOLD
