"""GitHub Copilot provider implementation."""

import asyncio
import json
import os
import re
import time
from typing import Dict, Optional, Tuple
from aiohttp import ClientSession

from .base import LLMProvider, estimate_tokens, calculate_cost

# GitHub OAuth client ID used by Copilot editors for device code flow
GITHUB_COPILOT_CLIENT_ID = "01ab8ac9400c4e429b23"


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
        self._pending_device_flow = None  # tracks an in-progress device auth

    def _load_github_token(self) -> Optional[str]:
        """Load the long-lived GitHub OAuth token from auth profile.

        Returns:
            str or None: The GitHub OAuth token, or None if not found.
        """
        if not os.path.exists(self.auth_profile_path):
            return None
        try:
            with open(self.auth_profile_path) as f:
                auth_data = json.load(f)
            return auth_data["profiles"]["github-copilot:github"]["token"]
        except (KeyError, json.JSONDecodeError):
            return None

    async def get_auth(self) -> Tuple[str, str]:
        """Get a valid GitHub Copilot API token, refreshing if needed.

        Returns:
            tuple[str, str]: (token, base_url)

        Raises:
            Exception: If no GitHub OAuth token is configured or token refresh fails.
                       When no OAuth token exists, the message suggests using !copilot-auth.
        """
        # Load cached token
        if os.path.exists(self.token_path):
            with open(self.token_path) as f:
                token_data = json.load(f)

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

        github_token = self._load_github_token()
        if not github_token:
            raise Exception(
                "No GitHub OAuth token configured. "
                "Use `!copilot-auth` to authenticate via device code flow."
            )

        # Exchange for new Copilot API token
        now_ms = time.time() * 1000
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
            json.dump(new_token_data, f, indent=2)

        self.bot.logger.info("Copilot token refreshed successfully")
        return token, self._extract_base_url(token)

    # ── Device Code Flow ──────────────────────────────────────────────

    async def start_device_flow(self) -> Dict:
        """Start a GitHub OAuth device code flow.

        Returns:
            dict: Contains 'device_code', 'user_code', 'verification_uri',
                  'interval', and 'expires_in' from GitHub.
        """
        async with ClientSession() as session:
            async with session.post(
                "https://github.com/login/device/code",
                headers={"Accept": "application/json"},
                data={
                    "client_id": GITHUB_COPILOT_CLIENT_ID,
                    "scope": "read:user",
                },
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(
                        f"Failed to start device flow: {resp.status} - {error_text}"
                    )
                data = await resp.json()

        self._pending_device_flow = data
        return data

    async def poll_device_flow(self) -> str:
        """Poll GitHub for device flow completion until the user authorizes.

        Must be called after start_device_flow(). Polls until the user enters
        the code or the flow expires.

        Returns:
            str: The GitHub OAuth access token on success.

        Raises:
            Exception: If the flow was not started, was denied, or expired.
        """
        if not self._pending_device_flow:
            raise Exception("No pending device flow. Call start_device_flow() first.")

        device_code = self._pending_device_flow["device_code"]
        interval = self._pending_device_flow.get("interval", 5)
        expires_in = self._pending_device_flow.get("expires_in", 900)
        deadline = time.time() + expires_in

        try:
            async with ClientSession() as session:
                while time.time() < deadline:
                    await asyncio.sleep(interval)

                    async with session.post(
                        "https://github.com/login/oauth/access_token",
                        headers={"Accept": "application/json"},
                        data={
                            "client_id": GITHUB_COPILOT_CLIENT_ID,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        },
                    ) as resp:
                        data = await resp.json()

                    error = data.get("error")
                    if error is None:
                        # Success
                        access_token = data["access_token"]
                        self._save_oauth_token(access_token)
                        self._pending_device_flow = None
                        return access_token

                    if error == "authorization_pending":
                        continue
                    if error == "slow_down":
                        interval = data.get("interval", interval + 5)
                        continue
                    if error in ("expired_token", "access_denied"):
                        raise Exception(f"Device flow {error.replace('_', ' ')}")

                    raise Exception(f"Device flow error: {error}")

            raise Exception("Device flow expired (timed out)")
        finally:
            self._pending_device_flow = None

    def _save_oauth_token(self, access_token: str) -> None:
        """Persist the GitHub OAuth token in the auth-profiles file.

        Args:
            access_token: GitHub OAuth access token to save.
        """
        auth_data = {"profiles": {}}
        if os.path.exists(self.auth_profile_path):
            try:
                with open(self.auth_profile_path) as f:
                    auth_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        auth_data.setdefault("profiles", {})
        auth_data["profiles"]["github-copilot:github"] = {
            "token": access_token,
            "updated_at": int(time.time()),
        }

        os.makedirs(os.path.dirname(self.auth_profile_path) or ".", exist_ok=True)
        with open(self.auth_profile_path, "w") as f:
            json.dump(auth_data, f, indent=2)

        # Invalidate cached API token so next get_auth() does a fresh exchange
        if os.path.exists(self.token_path):
            os.remove(self.token_path)

    def clear_auth(self) -> None:
        """Remove stored OAuth and API tokens."""
        for path in (self.auth_profile_path, self.token_path):
            if os.path.exists(path):
                os.remove(path)

    def auth_status(self) -> Dict:
        """Return current authentication status info.

        Returns:
            dict with keys:
                'has_oauth': bool - whether a GitHub OAuth token exists
                'has_api_token': bool - whether a cached API token exists
                'api_token_expires': float or None - expiry timestamp (ms)
                'api_token_valid': bool - whether API token is currently valid
        """
        has_oauth = self._load_github_token() is not None

        has_api_token = False
        api_token_expires = None
        api_token_valid = False
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path) as f:
                    token_data = json.load(f)
                has_api_token = True
                api_token_expires = token_data.get("expiresAt")
                if api_token_expires:
                    now_ms = time.time() * 1000
                    api_token_valid = (api_token_expires - now_ms) > 0
            except (json.JSONDecodeError, OSError):
                pass

        return {
            "has_oauth": has_oauth,
            "has_api_token": has_api_token,
            "api_token_expires": api_token_expires,
            "api_token_valid": api_token_valid,
        }

    async def chat(self, payload: Dict) -> Dict:
        """Send a chat completion request to GitHub Copilot API.

        Args:
            payload: Full request payload with 'messages', 'model', 'max_tokens' keys

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
