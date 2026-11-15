"""Store-time validation of enum settings: python -m unittest discover -s tests -p test_ai_settings.py."""

import os
import tempfile
import unittest

from modules.ai_cache import AICache


class ThinkingBackendValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_allowed_values_stored_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AICache(os.path.join(tmp, "logs"))
            ok, err = await cache.set_setting(1, 11, "glm_thinking_backend", "  Strata ")
            self.assertTrue(ok)
            self.assertIsNone(err)
            self.assertEqual(await cache.get_setting(1, 11, "glm_thinking_backend"), "strata")
            ok, err = await cache.set_setting(1, 11, "glm_thinking_backend", "off")
            self.assertTrue(ok)
            self.assertIsNone(err)
            await cache.close()

    async def test_bad_value_rejected_keeps_prior_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AICache(os.path.join(tmp, "logs"))
            await cache.set_setting(1, 11, "glm_thinking_backend", "strata")
            ok, err = await cache.set_setting(1, 11, "glm_thinking_backend", "starta")
            self.assertFalse(ok)
            self.assertIn("must be one of: off, strata", err)
            self.assertEqual(await cache.get_setting(1, 11, "glm_thinking_backend"), "strata")
            await cache.close()


if __name__ == "__main__":
    unittest.main()
