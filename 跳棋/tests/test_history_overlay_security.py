from __future__ import annotations

import unittest
from pathlib import Path


class HistoryOverlaySecurityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
        cls.formatter = (root / "static/js/chat_format.js").read_text(encoding="utf-8")
        cls.game = (root / "static/js/game.js").read_text(encoding="utf-8")

    def test_plain_model_text_cannot_create_move_overlay(self):
        start = self.formatter.index("function overlayFromText")
        body = self.formatter[start:start + 420]
        self.assertIn("return null", body)
        self.assertIn("prose is never trusted", body)

    def test_history_uses_persisted_rule_engine_metadata(self):
        self.assertIn("metadata.board_overlay", self.chat)
        self.assertIn("metadata.coach_report", self.chat)
        self.assertIn("currentOverlay(persistedOverlay)", self.chat)

    def test_overlay_is_revalidated_during_every_draw(self):
        draw_start = self.game.index("function drawAIAnalysisOverlay")
        draw_body = self.game[draw_start:draw_start + 500]
        self.assertIn("validateCurrentAIAnalysisOverlay", draw_body)


if __name__ == "__main__":
    unittest.main()
