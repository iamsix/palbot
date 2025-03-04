import asyncio
import discord
from discord.ext import commands
import re
import sqlite3
from urllib.parse import quote as uriquote
import html
from utils.formats import millify


CURR = ["AUD", "BRL", "CAD", "CHF", "CLP", "CNY", "CZK", "DKK", "EUR", 
        "GBP", "HKD", "HUF", "IDR", "ILS", "INR", "JPY", "KRW", "MXN", 
        "MYR", "NOK", "NZD", "PHP", "PKR", "PLN", "RUB", "SEK", "SGD", 
        "THB", "TRY", "TWD", "ZAR"]


class Finance(commands.Cog):
    yahoo_crumb = None
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def coin(self, ctx, *, line: str):
        await self.stock(ctx, name=line + "-usd")

    @commands.command()
    async def oldcoin(self, ctx, *, line: str):
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
                pUSD = data['price_usd']
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
    
    @commands.command(aliases=['stonks', 'stocks'])
    async def stock (self, ctx, *, name: str):
        """Look up a stock and show its current price, change, etc"""
        symbol = name

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/112.0",
                   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"}
        
        if not self.yahoo_crumb:
            url = "https://finance.yahoo.com/"
            async with self.bot.session.get(url, headers=headers) as resp:
                cookies = resp.cookies
            
            url = "https://query1.finance.yahoo.com/v1/test/getcrumb"
            async with self.bot.session.get(url, headers=headers, cookies=cookies) as resp:
                crumb = await resp.read()
                self.yahoo_crumb = crumb.decode()

        url = f'https://query1.finance.yahoo.com/v1/finance/search?q={uriquote(name)}&lang=en-US&region=US&newsCount=0'

        async with self.bot.session.get(url, headers=headers) as resp:
            try:
#                print(url)
                data = await resp.json(content_type=None)
#                data = await resp.read()
#                print(data)
#                data = json.loads(data)
                symbol = data['quotes'][0]['symbol']
            except Exception as e:
                print(e)
                symbol = name


        url = f"http://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}&crumb={self.yahoo_crumb}"
#        print(url)
        async with self.bot.session.get(url, headers=headers) as resp:
            data = await resp.json()
            if "quoteResponse" not in data:
                print(data)
            if not data["quoteResponse"]["result"]:
                await ctx.send(f"Unable to find a stonk named `{name}`")
                return
            data = data["quoteResponse"]["result"][0]


        cap = int(data.get('marketCap', 0))
        cap = millify(cap) if cap else "N/A"
        
        downup = "\N{CHART WITH UPWARDS TREND}" if data['regularMarketChange'] > 0 else "\N{CHART WITH DOWNWARDS TREND}"
        if  float(data['regularMarketChangePercent']) > 20.0:
            downup += "\N{ROCKET}"
        outstr = "{}{}: {} {} :: Cap: {} :: Today's change: {:.2f} ({:.2f}%) {}"
        longn = ' ({})'.format(data['shortName']) if 'shortName' in data else ''
        outstr = outstr.format(data['symbol'], longn, data['regularMarketPrice'], data['currency'], cap,
                               float(data['regularMarketChange']), float(data['regularMarketChangePercent']),
                               downup)
        
        if 'postMarketPrice' in data and (data['marketState'] == "CLOSED" or "POST" in data['marketState']):
            pdu = "\N{CHART WITH UPWARDS TREND}" if data['postMarketChange'] > 0 else "\N{CHART WITH DOWNWARDS TREND}"
            if  float(data['postMarketChangePercent']) > 20.0:
                pdu += "\N{ROCKET}"
            outstr += " :: After Hours: {:.2f} - Change: {:.2f} ({:.2f}%) {}".format(data['postMarketPrice'],
                        data['postMarketChange'], data['postMarketChangePercent'], pdu)

        await ctx.send(html.unescape(outstr))

            

async def setup(bot):
    await bot.add_cog(Finance(bot))
