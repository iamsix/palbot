from discord.ext import commands
from discord import app_commands
from pathlib import Path
from importlib import reload
import sys, traceback
from utils.time import human_timedelta
import logging
import discord

class UsefulEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener("on_reaction_add")
    @commands.Cog.listener("on_reaction_remove")
    async def on_reaction(self, reaction, user):
        self.bot.dispatch("reaction", reaction, user)

@app_commands.context_menu()
@commands.is_owner()
async def info(interaction: discord.Interaction, user: discord.Member):
    # unused for now as a context command for owner seems silly
    userinfo = interaction.client.utils.AuthorInfo(user)
    out = f"""location: {userinfo.location.__dict__ if userinfo.location else None}
    timezone: {userinfo.timezone}
    strava: {userinfo.strava}
    lastfm: {userinfo.lastfm}
    birthday: {userinfo.birthday}
    UID: {user.id}
    username: {user.name}
    display_name: {user.display_name}"""

    await interaction.response.send_message(out, ephemeral=True)


class OwnerCog(commands.Cog, name="Owner Commands"):

    def __init__(self, bot):
        self.bot = bot
        # self.bot.tree.add_command(info)

    def cog_unload(self):
        pass
        # self.bot.tree.remove_command(info)
    
    @commands.command()
    @commands.is_owner()
    @commands.guild_only()
    async def synctree(self, ctx):
        # commands = await self.bot.tree.sync(guild=ctx.guild)
        commands = await self.bot.tree.sync(guild=None)
        print(commands)
        # print(self.bot.tree)
        await ctx.send(f'Successfully synced {len(commands)} commands')

    # @commands.hybrid_command()
    async def testmessage(self, ctx, *, content):
        # ctx.message.content = ctx.message.content[6:]
        await ctx.send(f"content: {ctx.message}  {content}")


    @commands.command(hidden=True)
    @commands.is_owner()
    async def uptime(self, ctx):
        await ctx.send(f"Startup at {self.bot.uptime} : <t:{int(self.bot.uptime.timestamp())}:R>")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def playing(self, ctx, *, playing: str):
        await ctx.bot.change_presence(activity=discord.Game(name=playing))

    @commands.command(hidden=True)
    @commands.is_owner()
    async def watching(self, ctx, *, watching: str):
        await ctx.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=watching))

    @commands.command(hidden=True)
    @commands.is_owner()
    async def say(self, ctx, guild: int, *, message: str):
        chan = self.bot.get_channel(guild)
        await chan.send(message)
        

    @commands.command(hidden=True)
    @commands.is_owner()
    async def nick(self, ctx, *, nick):
        await ctx.guild.me.edit(nick=nick)


    @commands.command(hidden=True)
    @commands.is_owner()
    async def die(self, ctx):
        await ctx.send("Goodbye.")
        await self.bot.close()
    

    @commands.command(hidden=True)
    @commands.is_owner()
    async def loglevel(self, ctx, level):
        disclog = logging.getLogger('discord')
        if level.lower() == 'info':
            self.bot.logger.setLevel(logging.INFO)
            disclog.setLevel(logging.INFO)
        elif level.lower() == 'debug':
            self.bot.logger.setLevel(logging.DEBUG)
            disclog.setLevel(logging.DEBUG)
        elif level.lower() == 'warning':
            self.bot.logger.setLevel(logging.WARNING)
            disclog.setLevel(logging.WARNING)
        elif level.lower() == 'error':
            self.bot.logger.setLevel(logging.ERROR)
            disclog.logger.setLevel(logging.ERROR)
        elif level.lower() == 'critical':
            self.bot.logger.setLevel(logging.CRITICAL)
            disclog.setLevel(logging.CRITICAL)
        else:
            await ctx.send("Invalid logging level")
            return
        await ctx.send(f"Logging has been set to {level} {self.bot.logger.getEffectiveLevel()}")

    @commands.command(name='infotest', hidden=True)
    async def infotest(self, ctx, uid: int = None):
        if not uid:
            user = ctx.author
            userinfo = ctx.author_info
        else:
            user = self.bot.get_user(uid)
            userinfo = self.bot.utils.AuthorInfo(user)

        out = f"""location: {userinfo.location.__dict__}
        timezone: {userinfo.timezone}
        strava: {userinfo.strava}
        lastfm: {userinfo.lastfm}
        birthday: {userinfo.birthday}
        UID: {user.id}
        username: {user.name}
        display_name: {user.display_name}"""

        await ctx.send(out)


    # Hidden means it won't show up on the default help.
    @commands.command(name='load', hidden=True)
    @commands.is_owner()
    async def _load(self, ctx, *, cog: str):
        """Command which Loads a Module.
        Remember to use dot path. e.g: cogs.owner"""
        if "." not in cog:
            cog = f"{self.bot.moddir}.{cog}"
        try:
            await self.bot.load_extension(cog)
        except Exception as e:
            await ctx.send(f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('**`SUCCESS`**')

    @commands.command(name='unload', hidden=True)
    @commands.is_owner()
    async def _unload(self, ctx, *, cog: str):
        """Command which Unloads a Module.
        Remember to use dot path. e.g: cogs.owner"""
        if "." not in cog:
            cog = f"{self.bot.moddir}.{cog}"
        try:
            await self.bot.unload_extension(cog)
        except Exception as e:
            await ctx.send(f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('**`SUCCESS`**')

    @commands.group(name='reload', hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def _reload(self, ctx, *, cog: str):
        """Command which Reloads a Module.
        Remember to use dot path. e.g: cogs.owner"""
        if "." not in cog:
            cog = f"{self.bot.moddir}.{cog}"
        try:
            await self.bot.unload_extension(cog)
            await self.bot.load_extension(cog)
        except Exception as e:
            await ctx.send(f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send(f'{cog} **`SUCCESS`**')


    @_reload.command(name='all', hidden=True)
    async def _reload_all(self, ctx):
        """reload all modules in the module folder"""
        modlist = []
        for module in Path(self.bot.moddir).glob('*.py'):
            modlist.append(f"{self.bot.moddir}.{module.stem}")

        for module in modlist:
            try:
                self.bot.reload_extension(module)
            except Exception:
                await ctx.send(f"Failed to load module {module}")
                print(f'Failed to load cog {module}', file=sys.stderr)
                traceback.print_exc()
        mods = '\n'.join(modlist)
        await ctx.send(f"Reloaded:\n {mods}")

    @_reload.command(name='utils', hidden=True)
    async def _reload_utils(self, ctx):
        """Reload the bot.utils stuff"""
        self.bot.utils =  reload(self.bot.utils)

    @_reload.command(name='config', hidden=True)
    async def _reload_config(self, ctx):
        """Reload the bot.utils stuff"""
        self.bot.config =  reload(self.bot.config)


async def setup(bot):
    await bot.add_cog(OwnerCog(bot))
    await bot.add_cog(UsefulEvents(bot))
