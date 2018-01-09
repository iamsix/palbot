import urllib.request, urllib.error, urllib.parse
import json
import sqlite3
import re


CURR = ["AUD", "BRL", "CAD", "CHF", "CLP", "CNY", "CZK", "DKK", "EUR", 
        "GBP", "HKD", "HUF", "IDR", "ILS", "INR", "JPY", "KRW", "MXN", 
        "MYR", "NOK", "NZD", "PHP", "PKR", "PLN", "RUB", "SEK", "SGD", 
        "THB", "TRY", "TWD", "ZAR"]


def __init__(self):
     pass
#     newcoins()


def coin(self, e):
    coinqty = 1
    qtycheck = re.search("(^(\d*\.)?\d+)\s(\w.+)", e.input)
    if qtycheck:
        coinqty = float(qtycheck.group(1))
        e.input = qtycheck.group(3).strip()
    curr = ""
    cvtto = ""
    if " in " in e.input or " to " in e.input:
        if " in " in e.input:
            coin, cvtto = e.input.lower().split(" in ")
        elif " to " in e.input:
            coin, cvtto = e.input.lower().split(" to ")

        coinid = findcoin(coin)
        if cvtto.upper() in CURR:
            curr = "?convert={}".format(cvtto)
        
    else:
        coin = e.input.lower()
    
    coinid = findcoin(coin)
    if not coinid:
        e.output = 'Aye cannae find no "{}" coin'.format(coin)
        return

    url = "https://api.coinmarketcap.com/v1/ticker/{}{}".format(coinid, curr)
    results_json = get_coin_json(url)    
 
    cid = results_json[0]['symbol'].upper()
    name = results_json[0]['name']
    rank = results_json[0]['rank']
    pUSD = results_json[0]['price_usd']
    pC24 = results_json[0]['percent_change_24h']
    pC1 = results_json[0]['percent_change_1h']

    if cvtto:
        if curr:
            cvtval = "{:.2f}".format(float(results_json[0]['price_{}'.format(cvtto.lower())]) * coinqty)
        else:
            toid = findcoin(cvtto)
         
            if toid == "bitcoin":
                #api gives us BTC by default - its not in the currencies so that we get coin lookup on it and more than 2 decimal prescision
                cvtval = float(results_json[0]['price_btc']) * coinqty
                cvtto = "BTC"
            # convert to crypto
            else:
                url = "https://api.coinmarketcap.com/v1/ticker/{}".format(toid)
                tojson = get_coin_json(url)
                cvtto = tojson[0]['symbol'].upper()
                toval = float(tojson[0]['price_usd'])
                cvtval = "{:.8g}".format(from_to(toval, float(pUSD) * coinqty))
        if coinqty == 1:
            e.output = "{} {} | Value: {} {} (${} USD) | 1-hour change: {}% | 24-hour change: {}%".format(cid, name, cvtval, cvtto.upper(), pUSD, pC1, pC24)
        else:
            usdfinal = float(pUSD) * coinqty
            e.output = "{} {} : {:.8g} {} (${:.2f} USD)".format(coinqty, cid, float(cvtval), cvtto.upper(), usdfinal)
    else:
        if coinqty == 1:
            e.output = "{} {} | Value: ${} | 1-hour change: {}% | 24-hour change: {}%".format(cid, name, pUSD, pC1, pC24)
        else:
            finalprice = float(pUSD) * coinqty
            e.output = "{} {} : ${:.2f}".format(coinqty, cid, finalprice)
    
    return(e)
coin.command = "!coin"


def get_coin_json(url):
    request = urllib.request.Request(url)
   
    try: 
        response = urllib.request.urlopen(request)
    except urllib.error.HTTPError as err:
        self.logger.exception("Coin {} not found: {} {}".format(e.input, url, err))
        return
    
    results_json = json.loads(response.read().decode('utf-8'))
    return results_json


def from_to(tovalue, fromvalue):
    return fromvalue / tovalue


def findcoin(input): 
    conn = sqlite3.connect("coins.sqlite3")
    cursor = conn.cursor()
    like = "%{}%".format(input)
    result = cursor.execute("SELECT coinid FROM coins WHERE coinid = (?) OR symbol = (?) OR name LIKE (?)", (input, input, like)).fetchone()
    if result:
        return result[0]


def newcoins(line, nick, self, c):
    conn = sqlite3.connect("coins.sqlite3")
    cursor = conn.cursor()
    result = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='coins';").fetchone()
    if not result:
        cursor.execute("CREATE TABLE 'coins' ('symbol' TEXT, 'coinid' TEXT UNIQUE ON CONFLICT REPLACE, 'name' TEXT);")
        conn.commit()
    url = "https://api.coinmarketcap.com/v1/ticker/?limit=0"
    results_json = get_coin_json(url)

    for coin in results_json:
        sym = coin['symbol'].lower()
        cid = coin['id'].lower()
        name = coin['name'].lower()
        cursor.execute("insert into coins values (?, ?, ?)", (sym,cid,name))
        
    conn.commit()
    conn.close()
    return "Coin DB reloaded"
newcoins.admincommand = "newcoins"

