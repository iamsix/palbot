import json
import urllib.request
import datetime
from datetime import timedelta


TEAMS = {
	"ATL" : "Hawks",
	"BOS" : "Celtics",
	"BKN" : "Nets",
	"CHA" : "Hornets",
	"CHI" : "Bulls",
	"CLE" : "Cavaliers",
	"DAL" : "Mavericks",
	"DEN" : "Nuggets",
	"DET" : "Pistons",
	"GSW" : "Warriors",
	"HOU" : "Rockets",
	"IND" : "Pacers",
	"LAC" : "Clippers",
	"LAL" : "Lakers",
	"MEM" : "Grizzlies",
	"MIA" : "Heat",
	"MIL" : "Bucks",
	"MIN" : "Timberwolves",
	"NOP" : "Pelicans",
	"NYK" : "Knicks",
	"OKC" : "Thunder",
	"ORL" : "Magic",
	"PHI" : "Sixers",
	"PHX" : "Suns",
	"POR" : "Trail Blazers",
	"SAC" : "Kings",
	"SAS" : "Spurs",
	"TOR" : "Raptors",
	"UTA" : "Jazz",
	"WAS" : "Wizards"
}

def team(abbr):
    try:
        return TEAMS[abbr]
    except:
        return abbr

def get_nba_games(self, e):
    if e.input:
        if e.input.lower() == "tomorrow":
            gameday = datetime.date.today() + timedelta(days=1)
        elif e.input.lower() == "yesterday":
            gameday = datetime.date.today() - timedelta(days=1)
        else:
            gameday = datetime.datetime.strptime(e.input, "%Y-%m-%d")
    else:
        gameday = datetime.date.today()
         
    url = "https://data.nba.net/prod/v2/{}/scoreboard.json"
    url = url.format(gameday.strftime("%Y%m%d"))
    data = urllib.request.urlopen(url).read().decode()
    data = json.loads(data)
    
    games = []
    for game in data['games']:
        
        if game['statusNum'] == 1:
            # Game is scheduled in the future
            gametxt = "{} @ {} ({})"
            gametxt = gametxt.format(team(game['vTeam']['triCode']),
            	                     team(game['hTeam']['triCode']),
            	                     game['startTimeEastern'].replace(':00', ''))
            	                     
            	                     
        else:
            # game is finished or currently on
            gametxt = "{} {} - {} {} ({})"
            
            if game['statusNum'] == 2: 
                status = "{} Q{}".format(game['clock'], game['period']['current'])
            else:
                status = "Final"
                
            gametxt = gametxt.format(team(game['vTeam']['triCode']),
            	                     team(game['vTeam']['score']),
            	                     team(game['hTeam']['score']),
            	                     team(game['hTeam']['triCode']),
            	                     status)
        games.append(gametxt)
         
    e.output = " | ".join(games)
    return e
     

get_nba_games.command = "!nba"

#get_nba_games.input = "tomorrow"
#get_nba_games(None, get_nba_games)
#print(get_nba_games.output)

