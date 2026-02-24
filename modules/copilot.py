import aiohttp
import asyncio
import base64
import io
import json
import re
import time
from datetime import datetime
from discord.ext import commands
import discord
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
from modules.ai_cache import (AICache, SETTINGS_SPEC, SETTINGS_HELP,
                              GLOBAL_SETTINGS, SECRET_SETTINGS)
from modules.llm_providers import CopilotProvider, OpenAIProvider
from modules.context_gatherer import ContextGatherer

BOT_ADMIN_ROLE = "Bot Admin"

def is_bot_admin():
    """Check: bot owner OR has the Bot Admin role."""
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        return any(role.name == BOT_ADMIN_ROLE for role in ctx.author.roles)
    return commands.check(predicate)

async def _check_bot_admin(ctx) -> bool:
    """Inline check: bot owner OR has the Bot Admin role."""
    if await ctx.bot.is_owner(ctx.author):
        return True
    return any(role.name == BOT_ADMIN_ROLE for role in ctx.author.roles)


class Copilot(commands.Cog):
    DISCORD_EPOCH = 1420070400000  # Jan 1, 2015 in ms

    def __init__(self, bot):
        self.bot = bot
        self.ai_cache = AICache()
        self.provider = CopilotProvider(bot)
        self.glm_provider = OpenAIProvider(bot)
        self.context_gatherer = ContextGatherer(bot, self.ai_cache, self.provider)

    def cog_unload(self):
        asyncio.ensure_future(self.ai_cache.close())

    def resolve_mentions(self, ctx, text: str) -> str:
        """Replace Discord mention IDs with display names"""
        for user in ctx.message.mentions:
            text = text.replace(f'<@{user.id}>', user.display_name)
            text = text.replace(f'<@!{user.id}>', user.display_name)
        return text

    def restore_mentions(self, ctx, text: str) -> str:
        """Replace display names back to Discord mentions in output"""
        # Build name→mention map from message mentions + command author
        mention_map = {}
        for user in ctx.message.mentions:
            mention_map[user.display_name] = f'<@{user.id}>'
            if hasattr(user, 'name') and user.name != user.display_name:
                mention_map[user.name] = f'<@{user.id}>'
        # Always include the command invoker
        author = ctx.author
        mention_map[author.display_name] = f'<@{author.id}>'
        if hasattr(author, 'name') and author.name != author.display_name:
            mention_map[author.name] = f'<@{author.id}>'
        # Replace longest names first to avoid partial matches
        for name in sorted(mention_map, key=len, reverse=True):
            text = text.replace(name, mention_map[name])
        return text

    async def get_provider_auth(self):
        """Get authentication from provider.

        Returns tuple of (token, base_url) or raises on failure.
        """
        return await self.provider.get_auth()

