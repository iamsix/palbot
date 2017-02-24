import re
import urllib.request

def nba(self, e):
    url = "http://scores.espn.go.com/nba/bottomline/scores"
    request = urllib.request.urlopen(url)
    data = request.read().decode()

    data = data.replace("%20%20%20", " - ")
    data = data.replace('%20',' ').replace('^','').replace('&','\n')
    game = ""
    pattern = re.compile("nba_s_left\d+=(.*)")
    for match in re.findall(pattern, data):
        game = game + match + " | "
    game = game[:-2]

    e.output = game
nba.command = "!nba"

