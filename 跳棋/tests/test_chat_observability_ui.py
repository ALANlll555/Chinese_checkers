from __future__ import annotations

from pathlib import Path
import unittest


class ChatObservabilityUIContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
        cls.css = (root / "static/css/style.css").read_text(encoding="utf-8")

    def test_live_timer_is_visible_while_waiting(self):
        self.assertIn("chat-live-timer", self.chat)
        self.assertIn("performance.now()", self.chat)
        self.assertIn("0.0 秒", self.chat)

    def test_reasoning_and_mcp_are_independent_bubbles(self):
        self.assertIn("const roundUnits = new Map()", self.chat)
        self.assertIn("MCP 工具调用", self.chat)
        self.assertIn("renderMcpTrace", self.chat)
        self.assertIn("result_preview", self.chat)
        self.assertIn(".chat-unit", self.css)

    def test_game_settings_sync_into_chat_switches(self):
        self.assertIn("applyGameSettings", self.chat)
        self.assertIn("state?.deepseek_settings", self.chat)


if __name__ == "__main__":
    unittest.main()
