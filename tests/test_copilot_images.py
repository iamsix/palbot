"""Offline GLM vision regressions: python -m unittest discover -s tests -p test_copilot_images.py."""

import base64
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from modules.ai_cache import SETTINGS_SPEC
from modules.context_gatherer import ContextGatherer
from modules.copilot import Copilot, _IMAGE_HINT
from modules.llm_providers import OpenAIProvider


IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"x" * 100
IMAGE_URI = "data:image/png;base64," + base64.b64encode(IMAGE_BYTES).decode("ascii")


def attachment(filename="current.png"):
    return SimpleNamespace(
        content_type="image/png", filename=filename,
        read=AsyncMock(return_value=IMAGE_BYTES),
    )


class GLMImageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = {key: spec[0] for key, spec in SETTINGS_SPEC.items()}
        self.settings.update(glm_system_prompt="Custom GLM prompt", debug="on")
        self.author = SimpleNamespace(id=3, display_name="Alice", roles=[])
        self.mentioned = SimpleNamespace(id=4, display_name="Bob")
        self.message = SimpleNamespace(
            author=self.author, content="!glm describe <@4>",
            attachments=[], embeds=[], mentions=[self.mentioned],
        )
        self.history_messages = []
        self.history = Mock(side_effect=self.iter_history)
        self.ctx = SimpleNamespace(
            guild=SimpleNamespace(id=1), author=self.author,
            channel=SimpleNamespace(id=2, history=self.history, typing=AsyncMock),
            message=self.message, send=AsyncMock(), reply=AsyncMock(),
        )
        self.ctx.channel.typing = Mock(return_value=AsyncMock())
        bot = SimpleNamespace(
            user=SimpleNamespace(id=5, display_name="Palbot"),
            logger=Mock(), is_owner=AsyncMock(return_value=True),
        )
        self.ctx.bot = bot
        self.cog = Copilot.__new__(Copilot)
        self.cog.bot = bot
        self.cog.ai_cache = SimpleNamespace(
            get_setting=AsyncMock(side_effect=self.get_setting),
            get_all_settings=AsyncMock(return_value=self.settings),
            get_user_prompt=AsyncMock(return_value="Use friendly language"),
            log_usage=AsyncMock(),
            acl_is_allowed=AsyncMock(return_value=False),
            acl_is_enforced=AsyncMock(return_value=True),
        )
        self.cog.glm_provider = OpenAIProvider(bot)
        self.cog.glm_provider.chat = AsyncMock(return_value={
            "choices": [{"message": {
                "content": "Bob: a picture", "reasoning_content": "Visual reasoning",
            }}],
        })
        self.cog.context_gatherer = ContextGatherer(
            bot, self.cog.ai_cache, self.cog.glm_provider)
        self.cog.context_gatherer._build_compacted_context = AsyncMock(
            return_value="Recent channel conversation: history")
        self.cog.context_gatherer.gather_user_context = AsyncMock(return_value="Bob's context")
        self.cog.context_gatherer._estimate_image_tokens = Mock(return_value=100)
        self.cog._process_image_bytes = Mock(side_effect=lambda data, mime: (data, mime))
        self.cog._download_url = AsyncMock(return_value=(IMAGE_BYTES, "image/png"))
        self.cog._web_search = AsyncMock(
            return_value="<web_search_results>offline search</web_search_results>")

    async def get_setting(self, guild_id, channel_id, key):
        return self.settings[key]

    async def iter_history(self, *, limit, before):
        for message in self.history_messages[:limit]:
            yield message

    async def run_command(self, name):
        await getattr(Copilot, name).callback(self.cog, self.ctx, ask="describe <@4>")
        self.cog.glm_provider.chat.assert_awaited_once()
        return self.cog.glm_provider.chat.call_args.args[0]

    def reset_calls(self):
        self.cog.glm_provider.chat.reset_mock()
        self.cog.ai_cache.log_usage.reset_mock()
        self.history.reset_mock()
        self.ctx.send.reset_mock()

    async def test_image_payload_and_existing_command_behavior(self):
        for name in ("glm", "sglm"):
            with self.subTest(command=name):
                self.reset_calls()
                self.message.attachments = [attachment()]
                self.settings["glm_show_reasoning"] = "on"
                payload = await self.run_command(name)
                self.assertEqual(payload["model"], self.settings["glm_model"])
                self.assertEqual(payload["max_tokens"], self.settings["glm_max_output_tokens"])
                system, user = payload["messages"]
                self.assertIn("Custom GLM prompt", system["content"])
                self.assertIn("Use friendly language", system["content"])
                self.assertIn(_IMAGE_HINT, system["content"])
                self.assertEqual(user["content"][0], {
                    "type": "image_url", "image_url": {"url": IMAGE_URI},
                })
                text = user["content"][1]
                self.assertEqual(text["type"], "text")
                self.assertIn("<user_question>\ndescribe Bob\n</user_question>", text["text"])
                self.assertIn('type="discord_history"', text["text"])
                self.assertIn('type="mentioned_users"', text["text"])
                self.assertEqual("offline search" in text["text"], name == "sglm")
                self.history.assert_called_once_with(limit=10, before=self.message)
                usage = self.cog.ai_cache.log_usage.call_args
                self.assertEqual(usage.args[2], name)
                self.assertEqual(usage.args[3], len(text["text"]) // 4 + 100)
                output = self.ctx.send.call_args.args[0]
                self.assertIn("<@4>: a picture", output)
                self.assertIn("**Reasoning:** Visual reasoning", output)
                self.assertIn("imgs=1(~100tok)", output)
                self.assertNotIn(IMAGE_URI, output)
                self.cog.bot.logger.error.assert_not_called()

    async def test_no_images_keep_string_and_no_image_hint(self):
        for name in ("glm", "sglm"):
            with self.subTest(command=name):
                self.reset_calls()
                payload = await self.run_command(name)
                self.assertIsInstance(payload["messages"][1]["content"], str)
                self.assertNotIn(_IMAGE_HINT, payload["messages"][0]["content"])
                context = self.cog.context_gatherer.wrap_context(
                    "Recent channel conversation: history", "Bob's context")
                if name == "sglm":
                    context += "\n\n<web_search_results>offline search</web_search_results>"
                self.assertEqual(payload["messages"][1]["content"],
                                 f"{context}\n\n<user_question>\ndescribe Bob\n</user_question>")

    async def test_context_off_and_zero_lookback_disable_current_and_history_images(self):
        for name in ("glm", "sglm"):
            for context, lookback in (("off", 10), ("on", 0), ("off", 0)):
                with self.subTest(command=name, context=context, lookback=lookback):
                    self.reset_calls()
                    current = attachment()
                    prior = attachment("prior.png")
                    self.message.attachments = [current]
                    self.history_messages = [SimpleNamespace(
                        author=self.author, attachments=[prior], embeds=[], content="",
                    )]
                    self.settings.update(context=context, image_lookback=lookback)
                    payload = await self.run_command(name)
                    content = payload["messages"][1]["content"]
                    self.assertIsInstance(content, str)
                    self.history.assert_not_called()
                    current.read.assert_not_awaited()
                    prior.read.assert_not_awaited()
                    self.assertEqual('type="discord_history"' in content, context == "on")
                    self.assertNotIn(_IMAGE_HINT, payload["messages"][0]["content"])

    async def test_lookback_includes_prior_messages_and_current_message(self):
        for name in ("glm", "sglm"):
            with self.subTest(command=name):
                self.reset_calls()
                self.settings["image_lookback"] = 1
                self.message.attachments = [attachment()]
                included = attachment("included.png")
                excluded = attachment("excluded.png")
                self.history_messages = [
                    SimpleNamespace(author=self.author, attachments=[att], embeds=[], content="")
                    for att in (included, excluded)
                ]
                payload = await self.run_command(name)
                self.assertEqual([part["type"] for part in payload["messages"][1]["content"]],
                                 ["image_url", "image_url", "text"])
                self.history.assert_called_once_with(limit=1, before=self.message)
                included.read.assert_awaited_once()
                excluded.read.assert_not_awaited()
                self.message.attachments[0].read.assert_awaited_once()

    async def test_embed_and_raw_url_use_existing_download_helper(self):
        for name in ("glm", "sglm"):
            with self.subTest(command=name):
                self.reset_calls()
                self.cog._download_url.reset_mock()
                self.message.embeds = [SimpleNamespace(
                    type="image", thumbnail=None,
                    image=SimpleNamespace(
                        url="https://example.invalid/embed.png",
                        proxy_url="https://example.invalid/proxy.png",
                    ),
                )]
                self.message.content = "https://example.invalid/embed.png https://example.invalid/raw.png"
                payload = await self.run_command(name)
                self.assertEqual(len(payload["messages"][1]["content"]), 3)
                self.assertEqual(self.cog._download_url.await_count, 2)
                self.cog._download_url.assert_any_await("https://example.invalid/proxy.png")
                self.cog._download_url.assert_any_await("https://example.invalid/raw.png", probe=True)

    async def test_api_usage_takes_precedence_over_image_estimate(self):
        for name in ("glm", "sglm"):
            with self.subTest(command=name):
                self.reset_calls()
                self.message.attachments = [attachment()]
                self.cog.glm_provider.chat.return_value["usage"] = {
                    "prompt_tokens": 777, "completion_tokens": 22,
                }
                await self.run_command(name)
                self.assertEqual(self.cog.ai_cache.log_usage.call_args.args[3:5], (777, 22))

    async def test_image_budget_boundary_and_command_message_priority(self):
        self.settings["max_context_tokens"] = 5000
        old_uri = "data:image/png;base64," + base64.b64encode(b"old").decode("ascii")
        self.cog._collect_recent_images = AsyncMock(return_value=[
            {"url": old_uri, "tokens": 100}, {"url": IMAGE_URI, "tokens": 100},
        ])
        self.cog.glm_provider.estimate_tokens = Mock(return_value=2450)
        debug = []
        content, system, tokens = await self.cog._build_glm_user_content(
            self.ctx, "question", "system", self.settings, debug, True)
        self.assertEqual(content[0]["image_url"]["url"], IMAGE_URI)
        self.assertEqual(tokens, 100)
        self.assertIn(_IMAGE_HINT, system)
        self.assertIn("imgs_dropped=1(context_limit)", debug)
        self.cog._collect_recent_images.return_value = [{"url": IMAGE_URI, "tokens": 100}]
        self.cog.glm_provider.estimate_tokens.return_value = 2451
        content, system, tokens = await self.cog._build_glm_user_content(
            self.ctx, "question", "system", self.settings, [], False)
        self.assertEqual(content, "question")
        self.assertEqual(system, "system")
        self.assertEqual(tokens, 0)

    async def test_failed_download_keeps_text_request(self):
        self.message.attachments = [attachment()]
        self.message.attachments[0].read.side_effect = OSError("offline fixture failure")
        for name in ("glm", "sglm"):
            with self.subTest(command=name):
                self.reset_calls()
                payload = await self.run_command(name)
                self.assertIsInstance(payload["messages"][1]["content"], str)

    async def test_acl_blocks_collection_and_provider(self):
        self.cog.bot.is_owner.return_value = False
        self.message.attachments = [attachment()]
        for name in ("glm", "sglm"):
            with self.subTest(command=name):
                await getattr(Copilot, name).callback(self.cog, self.ctx, ask="picture?")
                self.cog.glm_provider.chat.assert_not_awaited()
                self.message.attachments[0].read.assert_not_awaited()
                self.history.assert_not_called()
                self.ctx.reply.assert_awaited()

    async def test_provider_failure_uses_existing_reporting(self):
        self.message.attachments = [attachment()]
        self.cog.glm_provider.chat.side_effect = RuntimeError("API error 429")
        for name in ("glm", "sglm"):
            with self.subTest(command=name):
                self.reset_calls()
                await self.run_command(name)
                output = self.ctx.send.call_args.args[0]
                self.assertIn("Rate limit hit", output)
                self.assertNotIn(IMAGE_URI, output)
                self.cog.bot.logger.error.assert_called()
                self.cog.ai_cache.log_usage.assert_not_awaited()

    async def test_shared_image_metadata_preserves_clai_payload(self):
        self.message.attachments = [attachment()]
        self.cog.provider = self.cog.glm_provider
        self.cog.get_provider_auth = AsyncMock(return_value=("offline", "https://example.invalid"))
        await Copilot.clai.callback(self.cog, self.ctx, ask="describe <@4>")
        payload = self.cog.provider.chat.call_args.args[0]
        self.assertEqual(payload["messages"][1]["content"][0], {
            "type": "image_url", "image_url": {"url": IMAGE_URI},
        })
        self.assertEqual(self.cog._img_tokens, 100)
        self.assertIn(_IMAGE_HINT, payload["messages"][0]["content"])
        self.cog.context_gatherer._estimate_image_tokens.assert_called_once_with(IMAGE_BYTES)


if __name__ == "__main__":
    unittest.main()
