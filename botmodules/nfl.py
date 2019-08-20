import requests
import datetime
import pytz


ET = pytz.timezone("US/Eastern")

def nfl(self, e):
    s = requests.session()

    r = s.post('https://api.nfl.com/v1/reroute', 
        data={'grant_type': 'client_credentials'},
        headers={'x-domain-id': '100'})    

    access_token = r.json()['access_token']

    url = ("https://api.nfl.com/v1/games?fs="
           "{id,gameTime,gameStatus,"
           "homeTeam{id,abbr,nickName},visitorTeam{id,abbr,nickName},"
           "homeTeamScore,visitorTeamScore}")
    r = s.get(url, headers={'authorization': 'Bearer ' + access_token}, 
                   timeout=3)

    data = r.json()['data']
    games = []
    for game in data:
        # TODO filter by date?
#        print(data, "\n ------ \n")
        starttime = datetime.datetime.strptime(game['gameTime'][:-3]+"00",
                                      "%Y-%m-%dT%H:%M:%S.%f%z")
        if starttime.date() != datetime.datetime.now().date():
            continue
        phase = game['gameStatus']['phase']
        if phase == "INGAME" or phase == "FINAL":
            games.append(format_ingame_or_final(game))            
        elif phase == "PREGAME":
            games.append(format_pregame(game))

    e.output = " | ".join(games)
    return e

nfl.command = "!nfl"


def format_ingame_or_final(game):
    if game['gameStatus']['phase'] == "INGAME":
        status = "{} Q{}".format(game['gameStatus']['gameClock'],
                                 game['gameStatus']['period'])
    else:
        status = "FINAL"

    fmt = "{} {} - {} {} ({})"
    out = fmt.format(game['visitorTeam']['nickName'],
                     game['visitorTeamScore']['pointsTotal'],
                     game['homeTeamScore']['pointsTotal'],
                     game['homeTeam']['nickName'],
                     status)
    return out

def format_pregame(game):
    # 2019-08-01T17:00:00.000-07:00 note the improper : in the GMT offset
    starttime = datetime.datetime.strptime(game['gameTime'][:-3]+"00",
                                      "%Y-%m-%dT%H:%M:%S.%f%z")
    starttime = starttime.astimezone(tz=ET)
    starttime = starttime.strftime('%-I:%M%p').replace(':00', '')
    # TODO include date?
    out = "{} @ {} ({})".format(game['visitorTeam']['nickName'],
                                 game['homeTeam']['nickName'],
                                 starttime)
    return out
    


nfl(None, nfl)
print(nfl.output)
