from __future__ import annotations

from pathlib import Path
import unittest


class ChatBubbleDefaultStateTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
        cls.css = (root / "static/css/style.css").read_text(encoding="utf-8")

    def test_live_reasoning_and_mcp_default_collapsed(self):
        start = self.chat.index("function renderTyping()")
        end = self.chat.index("function overlayForText")
        body = self.chat[start:end]

        self.assertIn(
            "className: 'chat-unit-reasoning is-active',\n      open: false",
            body,
        )
        self.assertIn(
            "className: 'chat-process-tool is-planning chat-unit-tool',\n        open: false",
            body,
        )
        self.assertIn(
            "className: 'chat-process-tool is-running chat-unit-tool',\n      open: false",
            body,
        )

    def test_historical_reasoning_and_mcp_default_collapsed(self):
        self.assertIn(
            "className: 'chat-unit-reasoning is-complete',\n      open: false",
            self.chat,
        )
        self.assertIn(
            "className: `chat-unit-tool ${call.success ? 'is-complete' : 'is-error'}`,\n      open: false",
            self.chat,
        )

    def test_final_results_default_expanded(self):
        for title in (
            "最终回答",
            "上下文与运行信息",
            "可验证 Coach 报告",
        ):
            title_index = self.chat.index(f"title: '{title}'")
            section = self.chat[title_index:title_index + 220]
            self.assertIn("open: true", section)

        candidate_index = self.chat.index(
            "title: `已验证候选 · ${meta.overlay.moves.length} 条`"
        )
        self.assertIn(
            "open: true",
            self.chat[candidate_index:candidate_index + 260],
        )

    def test_collapsed_rows_are_single_line_titles(self):
        self.assertIn(".chat-unit.is-collapsed .chat-unit-body", self.css)
        self.assertIn(".chat-unit.is-collapsed .chat-unit-summary", self.css)
        self.assertIn(".chat-unit-title", self.css)
        self.assertIn("white-space: nowrap", self.css)


if __name__ == "__main__":
    unittest.main()
