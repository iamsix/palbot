"""OpenAI-compatible provider implementation.

Supports OpenAI API-compatible endpoints (e.g., llama.cpp server, GLM-4.7 Flash).
"""

import time
from typing import Dict, Tuple
from aiohttp import ClientSession

from .base import LLMProvider, estimate_tokens, calculate_cost


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible API provider."""

    def __init__(self, bot, base_url: str = "https://llm.00id.net/v1", api_key: str = None):
        """Initialize OpenAI provider.

        Args:
            bot: Discord bot instance
            base_url: Base URL for API (default: https://llm.00id.net/v1)
            api_key: API key for authentication (optional)
        """
        self.bot = bot
        self.base_url = base_url
        self.api_key = api_key or "sk-no-key-required"  # Some servers don't require auth

    async def get_auth(self) -> Tuple[str, str]:
        """Get authentication credentials.

        Args:
            Returns:
                tuple[str, str]: (api_key, base_url)
        """
        return self.api_key, self.base_url

    async def chat(self, payload: Dict) -> Dict:
        """Send a chat completion request to OpenAI-compatible API.

        Args:
            payload: Full request payload with 'messages', 'model', 'max_tokens' keys

        Returns:
            dict: API response
        """
        api_key, base_url = await self.get_auth()

        async with ClientSession() as session:
            async with session.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"API error {resp.status}: {error_text[:200]}")
                return await resp.json()

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

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
