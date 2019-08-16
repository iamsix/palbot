import asyncio
import discord
from discord.ext import commands
import re
import sqlite3
from urllib.parse import quote as uriquote
import html


CURR = ["AUD", "BRL", "CAD", "CHF", "CLP", "CNY", "CZK", "DKK", "EUR", 
        "GBP", "HKD", "HUF", "IDR", "ILS", "INR", "JPY", "KRW", "MXN", 
        "MYR", "NOK", "NZD", "PHP", "PKR", "PLN", "RUB", "SEK", "SGD", 
        "THB", "TRY", "TWD", "ZAR"]


class Finance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.command()
    async def coin(self, ctx, *, line: str):
        """Look up a cryptocurrency such as Bitcoin
        Optionally specify a quantity such as `0.6 ETH`
        Optionally specify a conversion value such as `2 BTC in ETH` or `ETH in CAD`"""

        coin = await self.parse_coinline(line)
        if not coin:
            await ctx.send(f"Unable to find coin {line}")
            return

        url = f"https://api.coinmarketcap.com/v1/ticker/{coin['coin']}{coin['currency']}"
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            data = data[0]

        cid = data['symbol'].upper()
        name = data['name']
        pUSD = data['price_usd']
        pC24 = data['percent_change_24h']
        pC1 = data['percent_change_1h']
        output = ""
        if coin.get('cvtto', ''):
            cvtval = await self.convert_coin(coin, data)
            if not cvtval:
                await ctx.send(f"Failed to look up {coin['cvtto']}")
                return
            if coin['qty'] == 1:
                output = "{} {} | Value: {} {} (${} USD) | 1-hour change: {}% | 24-hour change: {}%".format(cid, name, cvtval, coin['cvtto'].upper(), pUSD, pC1, pC24)
            else:
                usdfinal = float(pUSD) * coin['qty']
                output = "{} {} : {} {} (${:.2f} USD)".format(coin['qty'], cid, cvtval, coin['cvtto'].upper(), usdfinal)
        else:
            if coin['qty'] == 1:
                output = "{} {} | Value: ${} | 1-hour change: {}% | 24-hour change: {}%".format(cid, name, pUSD, pC1, pC24)
            else:
                finalprice = float(pUSD) * coin['qty']
                output = "{} {} : ${:.2f}".format(coin['qty'], cid, finalprice)

        if output:
            await ctx.send(output)

    async def convert_coin(self, coin, data):
        if coin['currency']:
                cvtval = "{:.2f}".format(float(data['price_{}'.format(coin['cvtto'].lower())]) * coin['qty'])
        else:
            if not coin['cvtto']:
                cvtval = ''
            if coin['cvtto'] == "bitcoin":
                #api gives us BTC by default
                cvtval = self.ffstr(float(data['price_btc']) * coin['qty'])
                coin['cvtto'] = "BTC"
            else:
                url = "https://api.coinmarketcap.com/v1/ticker/{}".format(coin['cvtto'])
                async with self.bot.session.get(url) as resp:
                    tojson = await resp.json()
                    coin['cvtto'] = tojson[0]['symbol'].upper()
                    toval = float(tojson[0]['price_usd'])
                    cvtval = self.ffstr((float(pUSD) * coin['qty']) / toval)

        return cvtval

    def ffstr(self, number):
        return "{:.8f}".format(float(number)).rstrip('0').rstrip('.')


    async def parse_coinline(self, line):
        coinqty = 1
        qtycheck = re.search(r"(^(\d*\.)?\d+)\s?(\w.+)", line)
        if qtycheck:
            coinqty = float(qtycheck.group(1))
            line = qtycheck.group(3).strip()
        curr = ""
        cvtto = ""
        if " in " in line or " to " in line:
            if " in " in line:
                coin, cvtto = line.split(" in ")
            elif " to " in line:
                coin, cvtto = line.split(" to ")

            coinid = await self.findcoin(coin)
            if cvtto.upper() in CURR:
                curr = "?convert={}".format(cvtto)
            else:
                cvtto = await self.findcoin(cvtto)
        else:
            coin = line
        
        coinid = await self.findcoin(coin)
        if not coinid:
            return None

        return {'coin': coinid,
                'qty': coinqty,
                'currency': curr,
                'cvtto': cvtto}

    async def findcoin(self, coin): 
        conn = sqlite3.connect("coins.sqlite3")
        cursor = conn.cursor()
        result = cursor.execute("SELECT coinid FROM coins WHERE coinid = (?) OR symbol = (?)", (coin, coin)).fetchone()
        if not result:
            like = "%{}%".format(coin)
            result = cursor.execute("SELECT coinid FROM coins WHERE name LIKE (?)", [like]).fetchone()
        if result:
            return result[0]

    @commands.command(hidden=True)
    @commands.is_owner()
    async def newcoins(self, ctx):
        conn = sqlite3.connect("coins.sqlite3")
        cursor = conn.cursor()
        result = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='coins';").fetchone()
        if not result:
            cursor.execute("CREATE TABLE 'coins' ('symbol' TEXT, 'coinid' TEXT UNIQUE ON CONFLICT REPLACE, 'name' TEXT);")
            conn.commit()
        url = "https://api.coinmarketcap.com/v1/ticker/?limit=0"
        async with self.bot.session.get(url) as resp:
            data = await resp.json()

        for coin in data:
            sym = coin['symbol'].lower()
            cid = coin['id'].lower()
            name = coin['name'].lower()
            cursor.execute("insert into coins values (?, ?, ?)", (sym,cid,name))
            
        conn.commit()
        conn.close()
    
    @commands.command(aliases=['stonks'])
    async def stock (self, ctx, name: str):
        """Look up a stock and show its current price, change, etc"""
        symbol = ""
        url = f"https://autoc.finance.yahoo.com/autoc?query={uriquote(name)}&region=1&lang=en&guccounter=1"
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            for stock in data['ResultSet']['Result']:
                if stock['type'] == 'S':
                    symbol = stock['symbol']
                    break
        if not symbol:
            await ctx.send(f"Unable to find a stonk named `{name}`")
            return

        url = f"http://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
            data = data["quoteResponse"]["result"][0]

        outstr = "{}{}: {} {} :: Today's change: {:.2f} ({:.2f}%)"
        longn = ' ({})'.format(data['longName']) if 'longName' in data else ''
        outstr = outstr.format(data['symbol'], longn, data['regularMarketPrice'], data['currency'],
                            float(data['regularMarketChange']), float(data['regularMarketChangePercent']))
        
        if 'postMarketPrice' in data and (data['marketState'] == "CLOSED" or "POST" in data['marketState']):
            outstr += " :: After Hours: {:.2f} - Change: {:.2f}".format(data['postMarketPrice'],
                                                                        data['postMarketChange'])

        await ctx.send(html.unescape(outstr))

            

def setup(bot):
    bot.add_cog(Finance(bot))