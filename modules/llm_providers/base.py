"""Base class and utilities for LLM providers.

Defines the interface that all providers must implement.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Tuple


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def get_auth(self) -> Tuple[str, str]:
        """Return (token, base_url) for API authentication.

        Returns:
            tuple[str, str]: Authentication credentials
        """
        pass

    @abstractmethod
    async def chat(self, messages: List[Dict], model: str, max_tokens: int) -> Dict:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model identifier (e.g., 'claude-opus-4.6')
            max_tokens: Maximum tokens in response

        Returns:
            dict: Response from API with 'choices' containing message content and usage info
        """
        pass

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to estimate

        Returns:
            int: Estimated token count
        """
        pass

    @abstractmethod
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
        pass


# Token estimation utilities
def estimate_tokens(text: str) -> int:
    """Rough token count heuristic.

    Args:
        text: Text to estimate

    Returns:
        int: Estimated token count
    """
    return int(len(text) / 4)


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0
) -> float:
    """Calculate USD cost for an API call.

    Args:
        model: Model identifier
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cached_tokens: Number of tokens from cache (discounted rate)

    Returns:
        float: Cost in USD
    """
    # Default pricing (fallback)
    price_in, price_out, price_cache = 10.0, 30.0, 1.0

    # Provider-specific pricing
    if model.startswith("claude-opus"):
        price_in, price_out, price_cache = 5.0, 25.0, 0.50
    elif model.startswith("claude-sonnet"):
        price_in, price_out, price_cache = 3.0, 15.0, 0.30

    uncached_in = max(0, input_tokens - cached_tokens)
    return (uncached_in * price_in + cached_tokens * price_cache +
            output_tokens * price_out) / 1_000_000
