#!/usr/bin/env python3
"""
Test script for Copilot provider device code flow and auth management.
Tests the auth logic using mock data (no real GitHub API calls).
"""
import asyncio
import json
import os
import sys
import tempfile
import time

# Add repo root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeLogger:
    def info(self, msg): pass
    def error(self, msg): pass


class FakeConfig:
    def __init__(self, tmpdir):
        self.github_copilot_token_path = os.path.join(tmpdir, "token.json")
        self.github_copilot_auth_profile_path = os.path.join(tmpdir, "auth-profiles.json")


class FakeBot:
    def __init__(self, tmpdir):
        self.config = FakeConfig(tmpdir)
        self.logger = FakeLogger()


def test_auth_status_no_files():
    """auth_status returns correct state when no auth files exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        status = provider.auth_status()
        assert status["has_oauth"] is False, f"Expected has_oauth=False, got {status['has_oauth']}"
        assert status["has_api_token"] is False, f"Expected has_api_token=False, got {status['has_api_token']}"
        assert status["api_token_valid"] is False
        print("  ✅ auth_status: correct when no files exist")


def test_auth_status_with_oauth():
    """auth_status detects an existing OAuth token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        # Write an auth profile
        auth_data = {"profiles": {"github-copilot:github": {"token": "gho_test123"}}}
        with open(bot.config.github_copilot_auth_profile_path, "w") as f:
            json.dump(auth_data, f)

        status = provider.auth_status()
        assert status["has_oauth"] is True, f"Expected has_oauth=True, got {status['has_oauth']}"
        assert status["has_api_token"] is False
        print("  ✅ auth_status: detects OAuth token correctly")


def test_auth_status_with_valid_api_token():
    """auth_status reports a valid API token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        # Write an API token that expires in the future
        future_ms = (time.time() + 3600) * 1000
        token_data = {"token": "test_api_token", "expiresAt": future_ms}
        with open(bot.config.github_copilot_token_path, "w") as f:
            json.dump(token_data, f)

        status = provider.auth_status()
        assert status["has_api_token"] is True
        assert status["api_token_valid"] is True
        print("  ✅ auth_status: reports valid API token")


def test_auth_status_with_expired_api_token():
    """auth_status reports an expired API token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        # Write an API token that expired in the past
        past_ms = (time.time() - 3600) * 1000
        token_data = {"token": "test_api_token", "expiresAt": past_ms}
        with open(bot.config.github_copilot_token_path, "w") as f:
            json.dump(token_data, f)

        status = provider.auth_status()
        assert status["has_api_token"] is True
        assert status["api_token_valid"] is False
        print("  ✅ auth_status: reports expired API token")


def test_save_oauth_token():
    """_save_oauth_token writes the auth profile correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        provider._save_oauth_token("gho_new_token_123")

        with open(bot.config.github_copilot_auth_profile_path) as f:
            data = json.load(f)

        stored = data["profiles"]["github-copilot:github"]["token"]
        assert stored == "gho_new_token_123", f"Expected 'gho_new_token_123', got '{stored}'"
        assert "updated_at" in data["profiles"]["github-copilot:github"]
        print("  ✅ _save_oauth_token: writes token correctly")


def test_save_oauth_token_preserves_existing():
    """_save_oauth_token preserves other data in the auth profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        # Write existing auth data with extra keys
        existing = {
            "profiles": {
                "other-service": {"token": "keep_this"},
                "github-copilot:github": {"token": "old_token"},
            }
        }
        with open(bot.config.github_copilot_auth_profile_path, "w") as f:
            json.dump(existing, f)

        provider._save_oauth_token("gho_updated")

        with open(bot.config.github_copilot_auth_profile_path) as f:
            data = json.load(f)

        assert data["profiles"]["other-service"]["token"] == "keep_this"
        assert data["profiles"]["github-copilot:github"]["token"] == "gho_updated"
        print("  ✅ _save_oauth_token: preserves existing profiles")


def test_save_oauth_token_invalidates_api_token():
    """_save_oauth_token removes the cached API token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        # Write an existing API token
        with open(bot.config.github_copilot_token_path, "w") as f:
            json.dump({"token": "old", "expiresAt": 0}, f)

        provider._save_oauth_token("gho_new")

        assert not os.path.exists(bot.config.github_copilot_token_path), \
            "Expected API token file to be removed after saving new OAuth token"
        print("  ✅ _save_oauth_token: invalidates cached API token")


def test_clear_auth():
    """clear_auth removes both files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        # Create both files
        for path in (bot.config.github_copilot_token_path,
                     bot.config.github_copilot_auth_profile_path):
            with open(path, "w") as f:
                json.dump({}, f)

        provider.clear_auth()

        assert not os.path.exists(bot.config.github_copilot_token_path)
        assert not os.path.exists(bot.config.github_copilot_auth_profile_path)
        print("  ✅ clear_auth: removes both files")


def test_clear_auth_no_files():
    """clear_auth works when no files exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        # Should not raise
        provider.clear_auth()
        print("  ✅ clear_auth: no error when files don't exist")


def test_load_github_token_missing():
    """_load_github_token returns None when file is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        result = provider._load_github_token()
        assert result is None
        print("  ✅ _load_github_token: returns None when file missing")


def test_load_github_token_valid():
    """_load_github_token returns the token when present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        auth_data = {"profiles": {"github-copilot:github": {"token": "gho_abc"}}}
        with open(bot.config.github_copilot_auth_profile_path, "w") as f:
            json.dump(auth_data, f)

        result = provider._load_github_token()
        assert result == "gho_abc"
        print("  ✅ _load_github_token: returns token when present")


async def test_get_auth_no_oauth_raises():
    """get_auth raises a helpful error when no OAuth token exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        try:
            await provider.get_auth()
            assert False, "Should have raised"
        except Exception as e:
            assert "copilot-auth" in str(e).lower(), \
                f"Error should mention !copilot-auth, got: {e}"
        print("  ✅ get_auth: raises helpful error when no OAuth token")


async def test_get_auth_uses_cached_token():
    """get_auth returns cached token if still valid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        future_ms = (time.time() + 3600) * 1000
        token_data = {
            "token": "cached;proxy-ep=proxy.individual.githubcopilot.com",
            "expiresAt": future_ms,
        }
        with open(bot.config.github_copilot_token_path, "w") as f:
            json.dump(token_data, f)

        token, base_url = await provider.get_auth()
        assert token == token_data["token"]
        assert "githubcopilot.com" in base_url
        print("  ✅ get_auth: returns valid cached token without refresh")


def test_pending_device_flow_init():
    """Verify _pending_device_flow is None on init."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        assert provider._pending_device_flow is None
        print("  ✅ init: _pending_device_flow is None")


async def test_poll_without_start_raises():
    """poll_device_flow raises when no flow was started."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bot = FakeBot(tmpdir)
        from modules.llm_providers.copilot import CopilotProvider
        provider = CopilotProvider(bot)

        try:
            await provider.poll_device_flow()
            assert False, "Should have raised"
        except Exception as e:
            assert "start_device_flow" in str(e)
        print("  ✅ poll_device_flow: raises when no flow started")


if __name__ == "__main__":
    print("Copilot Auth Tests")
    print("=" * 50)

    # Synchronous tests
    print("\nSync tests:")
    test_auth_status_no_files()
    test_auth_status_with_oauth()
    test_auth_status_with_valid_api_token()
    test_auth_status_with_expired_api_token()
    test_save_oauth_token()
    test_save_oauth_token_preserves_existing()
    test_save_oauth_token_invalidates_api_token()
    test_clear_auth()
    test_clear_auth_no_files()
    test_load_github_token_missing()
    test_load_github_token_valid()
    test_pending_device_flow_init()

    # Async tests
    print("\nAsync tests:")
    asyncio.run(test_get_auth_no_oauth_raises())
    asyncio.run(test_get_auth_uses_cached_token())
    asyncio.run(test_poll_without_start_raises())

    print("\n" + "=" * 50)
    print("All tests completed!")
