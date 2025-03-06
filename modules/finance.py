from discord.ext import commands
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
                data = await resp.json(content_type=None)
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
