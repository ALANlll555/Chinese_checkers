from __future__ import annotations

from pathlib import Path
import unittest


class UpstreamDeltaUIContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
        cls.css = (root / "static/css/style.css").read_text(encoding="utf-8")
        cls.html = (root / "templates/index.html").read_text(encoding="utf-8")

    def test_reasoning_content_and_tool_arguments_have_delta_handlers(self):
        self.assertIn("case 'content_delta'", self.chat)
        self.assertIn("case 'tool_delta'", self.chat)
        self.assertIn("case 'upstream_done'", self.chat)
        self.assertIn("function addContentDelta", self.chat)
        self.assertIn("function toolDelta", self.chat)

    def test_live_drafts_are_separate_from_final_answer(self):
        self.assertIn("chat-process-draft-text", self.chat)
        self.assertIn("chat-process-tool is-planning", self.chat)
        self.assertIn(".chat-process-draft-text", self.css)
        self.assertIn(".chat-unit-answer", self.css)

    def test_official_effort_options_and_cache_version(self):
        for effort in ("low", "high", "xhigh", "max"):
            self.assertIn(f'value="{effort}"', self.html)
        self.assertIn('/static/js/chat.js?v=17', self.html)


if __name__ == "__main__":
    unittest.main()
