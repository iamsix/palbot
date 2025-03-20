import asyncio
import aiohttp
from socket import AF_INET
from aiohttp import ClientSession, ClientTimeout, TCPConnector

import discord
from discord.ext import commands
import config

from pathlib import Path

import datetime
import sys, traceback
import logging
import sqlite3
from collections import deque


FORMAT = "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
logging.basicConfig(filename='debug.log',level=logging.INFO, format=FORMAT)

intents = discord.Intents.all()
intents.members = True
intents.message_content = True

class PalBot(commands.Bot):

    def __init__(self):
        help = commands.DefaultHelpCommand(dm_help=None)
        help.verify_checks = False
        super().__init__(command_prefix=["!"],
                description="https://github.com/iamsix/palbot/ by six",
                case_insensitive=True,
                help_command=help,
                intents=intents)
        
        self.logger = logging.getLogger("palbot")
        self.moddir = "modules"
        self.config = __import__('config')
        self.utils = __import__('utils')
        # for the custom commands so I don't need to reopen the db each time
        self.cc_conn = None
        self.cc_c = None
        print(self.intents)
        print(self.intents.members)
        # This contains a list of tuples where:
        #  [0] = User's command Message obj
        #  [1] = the bot's response Message obj
        #  [2] = Paginator (None if not paginating)
        self.recent_posts = deque([], maxlen=10)
        



    async def setup_hook(self):
        try:
          connector = TCPConnector(family=AF_INET, limit_per_host=10)
          timeout = ClientTimeout(total=5)
          self.session = ClientSession(
                timeout=timeout,
                connector=connector,
                max_line_size=8190 * 2,
                max_field_size=8190 * 2,
                )
        except Exception as e:
            print(e)
        for module in Path(self.moddir).glob('*.py'):
            try:
                await self.load_extension("{}.{}".format(self.moddir,module.stem))
            except Exception as e:
                print(f'Failed to load cog {module}', file=sys.stderr)
                traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
        if 'Chat' in self.cogs:
            self.cc_conn = sqlite3.connect("customcommands.sqlite")
            self.cc_c = self.cc_conn.cursor()
            print("Chat loaded")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound) and self.cc_conn:
            # shouldn't happen too often.. I think checking the sqlite is better than
            # storing the entire command list in memory, even though it's likely small
            result = self.cc_c.execute(
                "SELECT cmd FROM commands WHERE cmd = (?)", 
                [ctx.invoked_with.lower()]).fetchone()
            
            if result:
                return
            self.logger.info(error)

        if hasattr(ctx.command, 'on_error'):
            return
        cog = ctx.cog
        if cog:
            if commands.Cog._get_overridden_method(cog.cog_command_error) is not None:
                return

        print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


    async def on_ready(self):
#        await self.async_init()
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.now(datetime.timezone.utc)
        print(f'Ready: {self.user} (ID: {self.user.id})')

    async def on_message(self, message):
        ctx = await self.get_context(message, cls=self.utils.MoreContext)
        # ctx.session = self.session
        await self.invoke(ctx)
    
    async def on_message_delete(self, message):
        remove = None
        # Consider iterating copy to prevent race condition
        for user_msg, bot_msg, pg in self.recent_posts:
            if message == user_msg:
                remove = (user_msg, bot_msg, pg)
                del(pg)
                await bot_msg.delete()
                break
        if remove:
            self.recent_posts.remove(remove)

    async def on_message_edit(self, before, after):
        # Consider iterating copy to prevent race condition
        for user_msg, bot_msg, pg in self.recent_posts:
            if before.id == user_msg.id:
                if pg:
                    pg.__del__()
                    del(pg)
                ctx = await self.get_context(after, cls=self.utils.MoreContext)
                ctx.override_send_for_edit = (after, bot_msg)
                await self.invoke(ctx)
                break
            
    def run(self):
        super().run(config.token, reconnect=True)

    async def close(self):
        await super().close()
        sys.exit()


bot = PalBot()
bot.run()
