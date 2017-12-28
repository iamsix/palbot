import urllib.request, urllib.error, urllib.parse
import json

url = "https://api.coinmarketcap.com/v1/ticker/"
SYMBOLS = {"eth": "ethereum", "btc": "bitcoin", "xrp": "ripple", 
           "bch": "bitcoin-cash", "ltc": "litecoin", "fun": "funfair"}


def coin(self, e):
    
    coin = e.input
    if coin in SYMBOLS:
        coin = SYMBOLS[coin]
    request = urllib.request.Request(url + coin)
    
    response = urllib.request.urlopen(request)
    
    results_json = json.loads(response.read().decode('utf-8'))
    
    id = results_json[0]['symbol']
    
    id = id.upper()
    rank = results_json[0]['rank']
    pUSD = results_json[0]['price_usd']
    pC24 = results_json[0]['percent_change_24h']
    pC1 = results_json[0]['percent_change_1h']
    
    e.output =  id + " | current price: $" + pUSD + ' | '  + "1-hour change: " + pC1 +'%' + ' | '  + "24-hour change: " + pC24 +'%'
    
    return(e)

coin.command = "!coin"
