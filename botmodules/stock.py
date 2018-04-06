import datetime
from datetime import timedelta
import json
import urllib.request, urllib.parse


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
        data = response['Time Series (Daily)']
        open = float(data[yesterday]['4. close'])
        close = float(data[today]['4. close'])

        change = close - open
        perc = (change / open) * 100


        e.output = "{} : {} || Today's Change: {:.2f} ({:.2f}%)".format(e.input, close, change, perc)
        

stock.command = "!stock"
