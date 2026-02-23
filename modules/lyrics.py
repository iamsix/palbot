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

                # Check if response is JSON
                content_type = resp.headers.get('content-type', '')
                if 'application/json' not in content_type:
                    await ctx.send("Error: Genius API returned HTML instead of JSON. Check your API token.")
                    return

                data = await resp.json()

            if not data['response']['hits']:
                await ctx.send(f"Could not find lyrics for `{query}` on Genius.")
                return

            # Get the first result
            song_id = data['response']['hits'][0]['result']['id']

            # Get lyrics from Genius API directly
            headers = {"Authorization": f"Bearer {genius_token}"}
            params = {"text_format": "dom"}

            async with self.bot.session.get(f"https://api.genius.com/songs/{song_id}", headers=headers, params=params) as resp:
                if resp.status != 200:
                    await ctx.send(f"Error accessing Genius lyrics API (status {resp.status}).")
                    return

                # Check if response is JSON
                content_type = resp.headers.get('content-type', '')
                if 'application/json' not in content_type:
                    await ctx.send("Error: Genius API returned HTML instead of JSON. Check your API token.")
                    return

                data = await resp.json()

            # Extract lyrics from the song data
            lyrics_data = data['response']['song']['lyrics']
            soup = BeautifulSoup(lyrics_data, 'html.parser')

            # Find the lyrics container
            lyrics_div = soup.find('div', class_='lyrics')
            if not lyrics_div:
                lyrics_div = soup.find('div', class_='lyrics__content')

            if not lyrics_div:
                lyrics_div = soup.find('div', {'data-lyrics-container': 'true'})

            if not lyrics_div:
                await ctx.send("Could not extract lyrics from the API response.")
                return

            # Extract lyrics from paragraphs
            paragraphs = lyrics_div.find_all('p')
            lines = []

            for p in paragraphs:
                p_text = p.get_text(strip=True)
                if p_text and not p_text.startswith('[') and not p_text.startswith('**'):
                    if not any(marker in p_text for marker in ['Contributors', 'Translations', 'Read More', 'Lyrics', 'Instrumental']):
                        lines.append(p_text)

            lines = [line.strip() for line in lines if line.strip()]

            # Truncate to ~15 lines
            max_lines = 15
            if len(lines) > max_lines:
                lines = lines[:max_lines]
                extra = len(lines) - max_lines
                if extra > 0:
                    lines.append(f"... ({extra} more lines)")
                lines.append(f"Full lyrics: https://genius.com/songs/{song_id}")

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
