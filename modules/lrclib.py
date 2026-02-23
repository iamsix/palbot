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
            !lyrics <song> - <artist>
            !lyrics <song> <artist>
        """
        # Parse query for song - artist format
        parts = query.split('-')
        song = parts[0].strip() if len(parts) > 0 else ""
        artist = parts[1].strip() if len(parts) > 1 else ""

        # Fallback: use entire query as search (both song and artist)
        if not song or not artist:
            await ctx.send("❌ Please provide both song and artist. Usage: `!lyrics <song> - <artist>`")
            return

        # Get LRCLIB API token (none needed, but keeping pattern for consistency)
        # Note: LRCLIB is free, no API key required

        try:
            # Step 1: Search for the song on LRCLIB
            search_url = "https://lrclib.net/api/get"
            params = {
                "artist_name": artist,
                "track_name": song
            }

            async with self.bot.session.get(search_url, params=params) as resp:
                if resp.status != 200:
                    await ctx.send(f"❌ Error searching for lyrics (status {resp.status}).")
                    return

                data = await resp.json()

            # Check if track was found
            if "message" in data and data["message"] == "Failed to find specified track":
                await ctx.send(f"❌ Could not find lyrics for `{song} - {artist}` on LRCLIB.")
                return

            # Extract lyrics data
            plain_lyrics = data.get("plainLyrics", "")
            synced_lyrics = data.get("syncedLyrics", "")
            track_name = data.get("trackName", song)
            artist_name = data.get("artistName", artist)
            instrumental = data.get("instrumental", False)

            # Handle instrumental tracks
            if instrumental:
                await ctx.send(f"🎵 `{track_name} - {artist_name}` is instrumental. No lyrics available.")
                return

            # Handle missing lyrics
            if not plain_lyrics:
                await ctx.send(f"❌ No lyrics found for `{track_name} - {artist_name}`.")
                return

            # Format output
            output = f"**{track_name} - {artist_name}**\n"
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
