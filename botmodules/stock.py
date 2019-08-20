import datetime
from datetime import timedelta
import json
import urllib.request, urllib.parse
import html


def stock (self, e):
    url = "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={}&apikey={}"
    if " " in e.input or "," in e.input:
        e.output = "I can only do a single stock symvol such as: AAPL"
    else:
        url = url.format(urllib.parse.quote(e.input), self.botconfig['APIkeys']['alphavantage'])
        response = urllib.request.urlopen(url)
        response = json.loads(response.read().decode('utf-8'))
        today = datetime.date.today().strftime("%Y-%m-%d")
        yesterday = (datetime.date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        symbol = response['Meta Data']["2. Symbol"]
        data = response['Time Series (Daily)']

        closed = False
        if today not in data:
           closed = True
           today = yesterday
           yesterday = (datetime.date.today() - timedelta(days=2)).strftime("%Y-%m-%d")

        current = float(data[today]['4. close'])
        close = float(data[yesterday]['4. close'])

        change = current - close
        perc = (change / current) * 100

        if not closed:
            e.output = "{} : {} || Today's Change: {:.2f} ({:.2f}%)".format(symbol, current, change, perc)
        else:
            e.output = "{} : {} || Yesterday's Change: {:.2f} ({:.2f}%) || MARKET CLOSED".format(symbol, current, change, perc)
          
        

stock.command = "!astock"


def ystock (self, e):
    # https://autoc.finance.yahoo.com/autoc?query=disney&region=1&lang=en
    url = "http://query1.finance.yahoo.com/v7/finance/quote?symbols={}"
    if " " in e.input:
        e.output = "I can only take a single stock quote for now"
        return

    url = url.format(urllib.parse.quote(e.input))
    response = urllib.request.urlopen(url)
    response = json.loads(response.read().decode('utf-8'))
    data = response["quoteResponse"]["result"][0]

    outstr = "{}{}: {} {} || Today's change: {:.2f} ({:.2f}%)"
    longn = ' ({})'.format(data['longName']) if 'longName' in data else ''
    outstr = outstr.format(data['symbol'], longn, data['regularMarketPrice'], data['currency'],
                           float(data['regularMarketChange']), float(data['regularMarketChangePercent']))
    
    if 'postMarketPrice' in data and (data['marketState'] == "CLOSED" or "POST" in data['marketState']):
        outstr += " || After Hours: {:.2f} - Change: {:.2f}".format(data['postMarketPrice'],
                                                                     data['postMarketChange'])

    e.output = html.unescape(outstr)

ystock.command = "!stock"
