import asyncio
from discord.ext import commands

class Weather(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    
    @commands.command(name='w')
    async def forecast_io(self, ctx, *, location:str = ""):
        pass

def setup(bot):
    bot.add_cog(Weather(bot))

