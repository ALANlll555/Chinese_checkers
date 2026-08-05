from __future__ import annotations

from pathlib import Path
import unittest


class SeparateReasoningBubblesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
        cls.css = (root / "static/css/style.css").read_text(encoding="utf-8")
        cls.deepseek = (root / "deepseek_chat.py").read_text(encoding="utf-8")

    def test_each_round_has_a_distinct_map_entry_and_title(self):
        self.assertIn("const roundUnits = new Map()", self.chat)
        self.assertIn("title: `第 ${round} 轮推理`", self.chat)
        self.assertIn("roundUnits.set(round, state)", self.chat)

    def test_collapsed_bubble_shows_title_only(self):
        self.assertIn(".chat-unit.is-collapsed .chat-unit-body", self.css)
        self.assertIn(".chat-unit.is-collapsed .chat-unit-summary", self.css)
        self.assertIn(".chat-unit.is-collapsed .chat-unit-state", self.css)
        self.assertIn(".chat-unit.is-collapsed .chat-unit-chevron", self.css)

    def test_history_uses_agent_transcript_rounds(self):
        self.assertIn("function reasoningRoundsFromMetadata", self.chat)
        self.assertIn("metadata.agent_messages", self.chat)
        self.assertIn(
            "reasoningRounds: reasoningRoundsFromMetadata(metadata)",
            self.chat,
        )

    def test_tool_identity_includes_model_round(self):
        self.assertIn(
            "`${normalizeRound(event.round || event.model_round)}:${Number(event.index || 0)}`",
            self.chat,
        )
        self.assertIn("model_round=round_index + 1", self.deepseek)
        self.assertIn('"model_round": round_index + 1', self.deepseek)


if __name__ == "__main__":
    unittest.main()
