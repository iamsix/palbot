import aiohttp
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
            params = {
                "q": query
            }

            self.bot.logger.info(f"Searching for lyrics: {query} (params: {params})")

            async with self.bot.session.get(search_url, params=params) as resp:
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
                await ctx.send(f"❌ **No Results Found**\nNo lyrics found for `{query}` on LRCLIB.")
                return

            # Step 2: Take the first result (best guess)
            first_result = data[0]
            self.bot.logger.info(f"Selected result: {first_result.get('trackName')} - {first_result.get('artistName')} (ID: {first_result.get('id')})")

            # Extract result data
            result_id = first_result.get("id")
            if not result_id:
                self.bot.logger.error(f"Result missing ID: {first_result}")
                await ctx.send(f"❌ **Invalid Result Format**\nAPI returned a result without an ID.")
                return

            track_name = first_result.get("trackName", query)
            artist_name = first_result.get("artistName", "Unknown Artist")
            album_name = first_result.get("albumName", "")
            instrumental = first_result.get("instrumental", False)

            # Step 3: Get lyrics using cached endpoint
            get_url = "https://lrclib.net/api/get-cached"
            params = {
                "id": result_id
            }

            self.bot.logger.info(f"Fetching lyrics for ID: {result_id}")

            async with self.bot.session.get(get_url, params=params) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    self.bot.logger.error(f"Get API error (status {resp.status}): {error_text}")
                    await ctx.send(f"❌ **Get API Error** (status {resp.status})\n{error_text[:200]}")
                    return

                try:
                    data = await resp.json()
                except Exception as json_err:
                    error_text = await resp.text()
                    self.bot.logger.error(f"Failed to parse get response: {json_err}")
                    await ctx.send(f"❌ **Invalid API Response**\nFailed to parse JSON from API.")
                    return

            # Check if track was found
            if "message" in data and data["message"] == "Failed to find specified track":
                self.bot.logger.warning(f"Track not found in cache: {result_id}")
                await ctx.send(f"❌ **Track Not Found**\nTrack `{track_name} - {artist_name}` not found in LRCLIB cache.")
                return

            # Extract lyrics data
            plain_lyrics = data.get("plainLyrics", "")
            synced_lyrics = data.get("syncedLyrics", "")

            # Handle instrumental tracks
            if instrumental:
                self.bot.logger.info(f"Instrumental track: {track_name} - {artist_name}")
                await ctx.send(f"🎵 **Instrumental Track**\n`{track_name} - {artist_name}` is instrumental. No lyrics available.")
                return

            # Handle missing lyrics
            if not plain_lyrics:
                self.bot.logger.warning(f"No lyrics returned for track: {track_name} - {artist_name}")
                await ctx.send(f"❌ **No Lyrics Available**\nNo lyrics found for `{track_name} - {artist_name}`.")
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
