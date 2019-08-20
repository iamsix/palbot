from discord.ext import commands
from pathlib import Path
from importlib import reload
import sys, traceback


class UsefulEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener("on_reaction_add")
    @commands.Cog.listener("on_reaction_remove")
    async def on_reaction(self, reaction, user):
        self.bot.dispatch("reaction", reaction, user)


class OwnerCog(commands.Cog, name="Owner Commands"):

    def __init__(self, bot):
        self.bot = bot


    @commands.command()
    @commands.is_owner()
    async def die(self, ctx):
        await ctx.send("Goodbye.")
        await self.bot.close()

    @commands.command(name='infotest', hidden=True)
    async def infotest(self, ctx):
        out = f"""location: {ctx.author_info.location.__dict__}
        timezone: {ctx.author_info.timezone}
        strava: {ctx.author_info.strava}
        lastfm: {ctx.author_info.lastfm}
        birthday: {ctx.author_info.birthday}"""

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
            self.bot.load_extension(cog)
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
            self.bot.unload_extension(cog)
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
            self.bot.unload_extension(cog)
            self.bot.load_extension(cog)
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


def setup(bot):
    bot.add_cog(OwnerCog(bot))
    bot.add_cog(UsefulEvents(bot))
