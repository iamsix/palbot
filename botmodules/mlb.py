import json
import urllib.request
import datetime
from datetime import timedelta
import pytz


ET = pytz.timezone("US/Eastern")

CARE = [
         144, #   'ATL',
         114, #   'CLE',
         147, #   'NYY',
         121, #   'NYM',
         111, #   'BOS',
         110, #   'BAL',
         133, #   'OAK',
         137, #   'SF',
         119, #   'LAD'
        ]

def get_mlb_games(self, e):
    if e.input:
        if e.input.lower() == "tomorrow":
            gameday = datetime.date.today() + timedelta(days=1)
        elif e.input.lower() == "yesterday":
            gameday = datetime.date.today() - timedelta(days=1)
        else:
            gameday = datetime.datetime.strptime(e.input, "%Y-%m-%d")
    else:
        gameday = datetime.date.today()

    url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=linescore,team"
    url += "&startDate={0}&endDate={0}".format(gameday)

    data = urllib.request.urlopen(url).read().decode()
    data = json.loads(data)
    data = data['dates'][0]['games']

    games = []
    for game in data:
        home = game['teams']['home']
        away = game['teams']['away']
        if away['team']['id'] in CARE or home['team']['id'] in CARE:
               code = game['status']['codedGameState']
               if code == "I": 
               # In progress
                   o = "{} {} - {} {} ({} {})".format(
                           away['team']['teamName'],away['score'],
                           home['score'],home['team']['teamName'],
                           game['linescore']['inningState'],
                           game['linescore']['currentInning'])
                   games.append(o)
               
               elif code == "F" or code == "O":
               #Final or Over whatever the difference is...
                   o = "{} {} - {} {} (Final)".format(
                           away['team']['teamName'],away['score'],
                           home['score'],home['team']['teamName'])
                   games.append(o)
               elif code == "D":
               #Delayed
                   o = "{} @ {} (Postponed)".format(away['team']['teamName'],
                                                    home['team']['teamName'])
                   games.append(o)
               elif code == "S":
               #Scheduled
                   starttime = datetime.datetime.strptime(game['gameDate'], "%Y-%m-%dT%H:%M:%SZ")
                   starttime = starttime.replace(tzinfo=pytz.utc).astimezone(tz=ET)
                   starttime = starttime.strftime('%I:%M%p').lstrip('0').replace(':00', '')

                   o = "{} @ {} ({} ET)".format(away['team']['teamName'],
                                             home['team']['teamName'],
                                             starttime)
                   games.append(o)


    e.output = " | ".join(games)
    return e
get_mlb_games.command = "!mlb"



#get_mlb_games({}, {})
