from __future__ import annotations

from pathlib import Path
import unittest


class ReasoningUIContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.html = (root / "templates/index.html").read_text(encoding="utf-8")
        cls.js = (root / "static/js/chat.js").read_text(encoding="utf-8")
        cls.css = (root / "static/css/style.css").read_text(encoding="utf-8")

    def test_reasoning_and_1m_switches_exist(self):
        self.assertIn('id="deepThinkToggle"', self.html)
        self.assertIn('id="context1mToggle"', self.html)
        self.assertIn("推理过程", self.html)
        self.assertIn("1M 上下文", self.html)

    def test_chat_sends_runtime_options(self):
        self.assertIn("thinking: preferences.thinking", self.js)
        self.assertIn("show_reasoning: preferences.showReasoning", self.js)
        self.assertIn("context_1m: preferences.context1m", self.js)

    def test_reasoning_is_collapsible_and_separate_from_board_evidence(self):
        self.assertIn("function renderReasoning", self.js)
        self.assertIn("reasoning_content", self.js)
        self.assertIn("不参与棋盘合法性与高亮判定", self.js)
        self.assertIn(".chat-reasoning", self.css)


if __name__ == "__main__":
    unittest.main()
