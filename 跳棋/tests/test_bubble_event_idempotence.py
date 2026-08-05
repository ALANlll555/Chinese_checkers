from __future__ import annotations

from pathlib import Path
import unittest


class BubbleEventIdempotenceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.chat = (root / "static/js/chat.js").read_text(encoding="utf-8")

    def test_non_delta_events_are_deduplicated(self):
        self.assertIn("const seenEvents = new Set()", self.chat)
        self.assertIn("function acceptEvent(event)", self.chat)
        self.assertIn("if (!acceptEvent(event)) return", self.chat)

    def test_finish_and_error_are_idempotent(self):
        self.assertIn("let finishApplied = false", self.chat)
        self.assertIn("if (finishApplied) return", self.chat)
        self.assertIn("let errorShown = false", self.chat)
        self.assertIn("if (errorShown) return", self.chat)

    def test_incoming_tokens_do_not_change_collapse_state(self):
        start = self.chat.index("function addReasoning")
        end = self.chat.index("function addContentDelta")
        self.assertNotIn("setCollapsed", self.chat[start:end])


if __name__ == "__main__":
    unittest.main()
