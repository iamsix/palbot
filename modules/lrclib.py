import aiohttp
from aiohttp import ClientTimeout

import re
from discord.ext import commands
from urllib.parse import quote as uriquote

class Lyrics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def lyrics(self, ctx, *, query: str):
        """Search for song lyrics using LRCLIB API

        Usage:
            !lyrics <song>
        """
        # Get LRCLIB API token (none needed, but keeping pattern for consistency)
        # Note: LRCLIB is free, no API key required

        try:
            
            # Step 1: Search for the song on LRCLIB (using only song title)
            search_url = "https://lrclib.net/api/search"
            headers = {
                "User-Agent": "PalbotDiscordBot/1.0 (https://github.com/Kpa-clawbot/palbot)"
            }
            params = {
                "q": query
            }

            self.bot.logger.info(f"Searching for lyrics: {query} (params: {params})")

            timeout = ClientTimeout(total=20)

            async with self.bot.session.get(search_url, 
                                            params=params, 
                                            headers=headers, 
                                            timeout=timeout
                                            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    self.bot.logger.error(f"Search API error (status {resp.status}): {error_text}")
                    await ctx.send(f"❌ **Search API Error** (status {resp.status})\n{error_text[:200]}")
                    return

                try:
                    data = await resp.json()
                except Exception as json_err:
                    error_text = await resp.text()
                    self.bot.logger.error(f"Failed to parse search response: {json_err}")
                    await ctx.send(f"❌ **Invalid API Response**\nFailed to parse JSON from API.")
                    return

            # Check if any results found
            if not data or len(data) == 0:
                self.bot.logger.warning(f"No lyrics found for query: {query}")
                # Escape Discord formatting in user input
                escaped_query = re.escape(query)
                await ctx.send(f"❌ **No Results Found**\nNo lyrics found for `{escaped_query}` on LRCLIB.")
                return

            # Step 2: Take the first result (best guess)
            first_result = data[0]
            self.bot.logger.info(f"Selected result: {first_result.get('trackName')} - {first_result.get('artistName')}")

            # Extract result data directly from search response (no second API call needed!)
            track_name = first_result.get("trackName", query)
            artist_name = first_result.get("artistName", "Unknown Artist")
            album_name = first_result.get("albumName", "")
            instrumental = first_result.get("instrumental", False)
            plain_lyrics = first_result.get("plainLyrics", "")
            synced_lyrics = first_result.get("syncedLyrics", "")

            # Handle instrumental tracks
            if instrumental:
                self.bot.logger.info(f"Instrumental track: {track_name} - {artist_name}")
                await ctx.send(f"🎵 **Instrumental Track**\n`{track_name} - {artist_name}` is instrumental. No lyrics available.")
                return

            # Handle missing lyrics
            if not plain_lyrics:
                self.bot.logger.warning(f"No lyrics returned for track: {track_name} - {artist_name}")
                # Escape Discord formatting
                escaped_track = re.escape(track_name)
                escaped_artist = re.escape(artist_name)
                await ctx.send(f"❌ **No Lyrics Available**\nNo lyrics found for `{escaped_track} - {escaped_artist}`.")
                return

            # Format output
            output = f"**{track_name} - {artist_name}**"
            if album_name:
                output += f" ({album_name})"
            output += "\n"
            output += "-" * 40 + "\n\n"
            output += plain_lyrics

            # Optional: Add synced lyrics link
            if synced_lyrics:
                output += f"\n\n*Synced lyrics available via LRCLIB*"

            # TRUNCATE to Discord's 2000 character limit
            MAX_DISCORD_MESSAGE_LENGTH = 2000
            if len(output) > MAX_DISCORD_MESSAGE_LENGTH:
                self.bot.logger.warning(f"Lyrics too long ({len(output)} chars), truncating to {MAX_DISCORD_MESSAGE_LENGTH}")
                output = output[:MAX_DISCORD_MESSAGE_LENGTH - 3] + "..."

            # Send with limit
            await ctx.send(output)

        except aiohttp.ClientError as e:
            error_msg = f"Network error: {type(e).__name__} - {str(e)}"
            self.bot.logger.error(error_msg, exc_info=True)
            await ctx.send(f"❌ **Network Error**\n{error_msg}")
        except Exception as e:
            error_msg = f"Unexpected error: {type(e).__name__} - {str(e)}"
            self.bot.logger.error(error_msg, exc_info=True)
            await ctx.send(f"❌ **Unexpected Error**\n{error_msg}")

async def setup(bot):
    await bot.add_cog(Lyrics(bot))
