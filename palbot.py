import asyncio
import aiohttp

import discord
from discord.ext import commands
import config

from pathlib import Path

import datetime
import sys, traceback
import logging


FORMAT = "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
logging.basicConfig(filename='debug.log',level=logging.INFO, format=FORMAT)


class PalBot(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix=["$"],
                description="https://github.com/iamsix/palbot/",
                pm_help=None, help_attrs=dict(hidden=True),
                fetch_offline_members=False, case_insensitive=True)
        self.loop = asyncio.get_event_loop()
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.logger = logging.getLogger("palbot")
        self.moddir = "modules"
        self.config = __import__('config')
        self.utils = __import__('utils')
#        self.lastresponses = deque((command, myresponse), maxlen=50))

        for module in Path(self.moddir).glob('*.py'):
            try:
                self.load_extension("{}.{}".format(self.moddir,module.stem))
            except Exception as e:
                print(f'Failed to load cog {module}', file=sys.stderr)
                print(e)
                traceback.print_exc()



    async def on_ready(self):
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.utcnow()
        print(f'Ready: {self.user} (ID: {self.user.id})')

    async def on_message(self, message):
        ctx = await self.get_context(message, cls=self.utils.MoreContext)
        await self.invoke(ctx)

    def run(self):
        super().run(config.token, reconnect=True)

    async def close(self):
        await super().close()
        await self.session.close()


bot = PalBot()
bot.run()
