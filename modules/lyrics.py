import aiohttp
import re
from discord.ext import commands
from bs4 import BeautifulSoup
from urllib.parse import quote as uriquote
import html2text

class Lyrics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def handle_config(self, ctx, *, token: str = None):
        """Handle config command - show current status or set new token"""
        if token:
            # Set the new token
            self.bot.config.genius_token = token
            await ctx.send(f"Genius API token updated successfully.")
        else:
            # Show current status
            current_token = self.bot.config.genius_token
            if current_token:
                await ctx.send(f"Genius API is configured.")
            else:
                await ctx.send("Genius API is not configured. Use `!lyrics config <token>` to set one.")

    @commands.command()
    async def lyrics(self, ctx, *, query: str):
        """Search for song lyrics using Genius API

        Usage:
            !lyrics <song> - <artist>
            !lyrics <search query>
            !lyrics config
            !lyrics config <token>
        """
        # Handle config command
        if query.lower() == 'config':
            return await self.handle_config(ctx)

        # Parse query for song - artist format
        parts = query.split('-')
        song = parts[0].strip() if len(parts) > 0 else ""
        artist = parts[1].strip() if len(parts) > 1 else ""

        # Fallback: use entire query as search
        if not song:
            song = query

        # Get Genius API token
        genius_token = self.bot.config.genius_token
        if not genius_token:
            await ctx.send("Genius API token not set. Use `!lyrics config <token>` to set one.")
            return

        try:
            # Step 1: Search for the song on Genius
            search_url = "https://api.genius.com/search"
            headers = {"Authorization": f"Bearer {genius_token}"}
            params = {"q": f"{song} {artist}" if artist else song}

            async with self.bot.session.get(search_url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    await ctx.send(f"Error searching for lyrics on Genius (status {resp.status}).")
                    return

                data = await resp.json()

            if not data['response']['hits']:
                await ctx.send(f"Could not find lyrics for `{query}` on Genius.")
                return

            # Get the first result
            song_path = data['response']['hits'][0]['result']['path']
            song_url = f"https://genius.com{song_path}"

            # Scrape lyrics from the Genius page
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            async with self.bot.session.get(song_url, headers=headers) as resp:
                if resp.status != 200:
                    await ctx.send(f"Error accessing Genius lyrics page (status {resp.status}).")
                    return

                html = await resp.text()

            # Parse HTML and extract lyrics
            soup = BeautifulSoup(html, 'html.parser')

            # Find all lyrics containers
            lyrics_divs = soup.find_all('div', {'data-lyrics-container': 'true'})

            if not lyrics_divs:
                await ctx.send("Could not find lyrics container in the page.")
                return

            lines = []

            for div in lyrics_divs:
                # Find all ReferentFragment links with lyrics
                lyric_links = div.find_all('a', class_='ReferentFragment-desktop__ClickTarget')

                for link in lyric_links:
                    # Get the text from the Highlight span
                    highlight = link.find('span', class_='ReferentFragment-desktop__Highlight')
                    if highlight:
                        text = highlight.get_text(strip=True)
                        # Filter out metadata markers
                        if text and not text.startswith('[') and not text.startswith('**'):
                            if not any(marker in text for marker in ['Contributors', 'Translations', 'Read More', 'Instrumental']):
                                lines.append(text)

            lines = [line.strip() for line in lines if line.strip()]

            # Truncate to ~15 lines
            max_lines = 15
            if len(lines) > max_lines:
                lines = lines[:max_lines]
                extra = len(lines) - max_lines
                if extra > 0:
                    lines.append(f"... ({extra} more lines)")
                lines.append(f"Full lyrics: {song_url}")

            # Format output
            output = f"**{song}{' - ' + artist if artist else ''}**\n"
            output += "-" * 40 + "\n"
            output += "\n".join(lines)

            await ctx.send(output)

        except Exception as e:
            self.bot.logger.error(f"Lyrics command error: {e}")
            await ctx.send(f"Error retrieving lyrics: {str(e)}")

async def setup(bot):
    await bot.add_cog(Lyrics(bot))
