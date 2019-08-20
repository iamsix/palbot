import requests
import pytz
import datetime

ET = pytz.timezone("US/Eastern")


def owl(self, e):
    url = "https://api.overwatchleague.com/live-match"
    data = requests.get(url, timeout=3).json()['data']

    if data['liveMatch']:
        match = data['liveMatch']
        if match['status'] == "PENDING":
            e.output = format_pending_game(match)
        else:
            game = None
            for g in match['games']:
                if g['status'] == "IN_PROGRESS":
                    game = g['number']
            if game:
                status = "Map {} of {}".format(game, 
                        match['conclusionValue'])
            else:
                status = "Intermission"
            fmt = "{} {} - {} {} ({})"
            e.output = fmt.format(match['competitors'][0]['name'],
                                  match['scores'][0]['value'],
                                  match['scores'][1]['value'],
                                  match['competitors'][1]['name'],
                                  status)
    if data['nextMatch']:
        match = data['nextMatch']
        e.output += " | {}".format(format_pending_game(match))

    return e

owl.command = "!owl"


def format_pending_game(match):
    starttime = datetime.datetime \
                        .strptime(match['startDate'],  
                                "%Y-%m-%dT%H:%M:%S.%fZ") \
                        .replace(tzinfo=pytz.utc) \
                        .astimezone(tz=ET)
    status = starttime.strftime('%-d %b at %-I:%M%p').replace(':00', '')

    fmt = "{} vs {} ({} ET)"
    return fmt.format(match['competitors'][0]['name'],
                             match['competitors'][1]['name'],
                             status)

# entire schedule for the entire year for some reason
# could maybe filter down from this? might want to cache it
#url = "https://api.overwatchleague.com/schedule" 
