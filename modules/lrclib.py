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

            async with self.bot.session.get(search_url, params=params) as resp:
                if resp.status != 200:
                    await ctx.send(f"❌ Error searching for lyrics (status {resp.status}).")
                    return

                data = await resp.json()

            # Check if any results found
            if not data or len(data) == 0:
                await ctx.send(f"❌ No lyrics found for `{query}` on LRCLIB.")
                return

            # Step 2: Take the first result (best guess)
            first_result = data[0]

            # Extract result data
            result_id = first_result.get("id")
            track_name = first_result.get("trackName", query)
            artist_name = first_result.get("artistName", "Unknown Artist")
            album_name = first_result.get("albumName", "")
            instrumental = first_result.get("instrumental", False)

            # Step 3: Get lyrics using cached endpoint
            get_url = "https://lrclib.net/api/get-cached"
            params = {
                "id": result_id
            }

            async with self.bot.session.get(get_url, params=params) as resp:
                if resp.status != 200:
                    await ctx.send(f"❌ Error getting lyrics (status {resp.status}).")
                    return

                data = await resp.json()

            # Check if track was found
            if "message" in data and data["message"] == "Failed to find specified track":
                await ctx.send(f"❌ Could not find lyrics for `{track_name} - {artist_name}` on LRCLIB.")
                return

            # Extract lyrics data
            plain_lyrics = data.get("plainLyrics", "")
            synced_lyrics = data.get("syncedLyrics", "")

            # Handle instrumental tracks
            if instrumental:
                await ctx.send(f"🎵 `{track_name} - {artist_name}` is instrumental. No lyrics available.")
                return

            # Handle missing lyrics
            if not plain_lyrics:
                await ctx.send(f"❌ No lyrics found for `{track_name} - {artist_name}`.")
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

        except Exception as e:
            self.bot.logger.error(f"Lyrics command error: {e}")
            await ctx.send(f"❌ Error retrieving lyrics: {str(e)}")

async def setup(bot):
    await bot.add_cog(Lyrics(bot))
