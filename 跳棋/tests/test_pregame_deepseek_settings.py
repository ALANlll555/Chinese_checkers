from __future__ import annotations

from pathlib import Path
import unittest


class PreGameDeepSeekSettingsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.html = (root / "templates/index.html").read_text(encoding="utf-8")
        cls.game = (root / "static/js/game.js").read_text(encoding="utf-8")
        cls.app = (root / "app.py").read_text(encoding="utf-8")

    def test_all_pre_game_settings_are_present(self):
        for control in (
            "apiKeyInput",
            "deepseekBaseUrlInput",
            "deepseekModelInput",
            "deepseekThinkingInput",
            "deepseekShowReasoningInput",
            "deepseekContext1mInput",
            "deepseekStrictToolsInput",
            "deepseekReasoningEffortSelect",
            "deepseekMaxTokensInput",
        ):
            self.assertIn(f'id="{control}"', self.html)

    def test_new_game_sends_complete_settings(self):
        self.assertIn("collectDeepSeekSettings(true)", self.game)
        self.assertIn("deepseek_settings: deepseekSettings", self.game)
        self.assertIn("DEEPSEEK_SETUP_STORAGE", self.game)

    def test_backend_keeps_api_key_out_of_public_settings(self):
        self.assertIn("_normalize_deepseek_settings", self.app)
        self.assertIn("_public_deepseek_settings", self.app)
        self.assertIn('normalized.pop("api_key", None)', self.app)
        self.assertIn("/api/deepseek/test", self.app)


if __name__ == "__main__":
    unittest.main()
