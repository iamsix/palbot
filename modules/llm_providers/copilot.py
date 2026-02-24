"""GitHub Copilot provider implementation."""

import re
import time
from typing import Dict, Tuple
from aiohttp import ClientSession

from .base import LLMProvider, estimate_tokens, calculate_cost


class CopilotProvider(LLMProvider):
    """GitHub Copilot API provider."""

    def __init__(self, bot):
        """Initialize Copilot provider.

        Args:
            bot: Discord bot instance (for config and logging)
        """
        self.bot = bot
        self.token_path = bot.config.github_copilot_token_path
        self.auth_profile_path = bot.config.github_copilot_auth_profile_path

    async def get_auth(self) -> Tuple[str, str]:
        """Get a valid GitHub Copilot API token, refreshing if needed.

        Returns:
            tuple[str, str]: (token, base_url)
        """
        # Load cached token
        with open(self.token_path) as f:
            token_data = __import__('json').load(f)

        # Check if token is still valid (with 5 min buffer)
        expires_at = token_data.get("expiresAt", 0)
        now_ms = time.time() * 1000

        if expires_at - now_ms > 5 * 60 * 1000:
            # Token still valid
            token = token_data["token"]
            base_url = self._extract_base_url(token)
            return token, base_url

        # Token expired or expiring soon - refresh it
        self.bot.logger.info("Copilot token expired, refreshing...")

        # Load the GitHub OAuth token from auth profile
        with open(self.auth_profile_path) as f:
            auth_data = __import__('json').load(f)

        github_token = auth_data["profiles"]["github-copilot:github"]["token"]

        # Exchange for new Copilot API token
        async with ClientSession() as session:
            async with session.get(
                "https://api.github.com/copilot_internal/v2/token",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {github_token}",
                    "Editor-Version": "vscode/1.96.2",
                    "User-Agent": "GitHubCopilotChat/0.26.7",
                }
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Token refresh failed: {resp.status} - {error_text}")

                data = await resp.json()
                token = data["token"]
                # GitHub returns seconds, convert to ms
                expires_at_raw = data["expires_at"]
                if expires_at_raw > 10_000_000_000:
                    expires_at = expires_at_raw  # already ms
                else:
                    expires_at = expires_at_raw * 1000

        # Save refreshed token
        new_token_data = {
            "token": token,
            "expiresAt": expires_at,
            "updatedAt": int(now_ms),
        }
        with open(self.token_path, 'w') as f:
            __import__('json').dump(new_token_data, f, indent=2)

        self.bot.logger.info("Copilot token refreshed successfully")
        return token, self._extract_base_url(token)

    async def chat(self, messages: Dict, model: str, max_tokens: int) -> Dict:
        """Send a chat completion request to GitHub Copilot API.

        Args:
            messages: Request payload with 'messages', 'model', 'max_tokens'
            model: Model identifier
            max_tokens: Maximum tokens in response

        Returns:
            dict: API response
        """
        token, base_url = await self.get_auth()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Copilot-Integration-Id": "vscode-chat",
            "Editor-Version": "vscode/1.95.0",
        }

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        async with ClientSession() as session:
            async with session.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"API error {resp.status}: {error_text[:200]}")
                return await resp.json()

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses the same heuristic as the base class.

        Args:
            text: Text to estimate

        Returns:
            int: Estimated token count
        """
        return estimate_tokens(text)

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0
    ) -> float:
        """Calculate API cost for a request.

        Args:
            model: Model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cached_tokens: Number of tokens from cache (discounted rate)

        Returns:
            float: Cost in USD
        """
        return calculate_cost(model, input_tokens, output_tokens, cached_tokens)

    def _extract_base_url(self, token: str) -> str:
        """Extract API base URL from token's proxy-ep field.

        Args:
            token: Copilot API token

        Returns:
            str: Base URL for API calls
        """
        match = re.search(r'proxy-ep=([^;\s]+)', token)
        if match:
            proxy_ep = match.group(1)
            return "https://" + proxy_ep.replace("proxy.", "api.")
        return "https://api.individual.githubcopilot.com"
