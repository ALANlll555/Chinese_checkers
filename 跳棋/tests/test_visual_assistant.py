from __future__ import annotations

import unittest
from pathlib import Path


class VisualAssistantContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.html = (root / "templates" / "index.html").read_text(encoding="utf-8")
        cls.css = (root / "static" / "css" / "style.css").read_text(encoding="utf-8")
        cls.game_js = (root / "static" / "js" / "game.js").read_text(encoding="utf-8")
        cls.chat_js = (root / "static" / "js" / "chat.js").read_text(encoding="utf-8")
        cls.format_js = (root / "static" / "js" / "chat_format.js").read_text(encoding="utf-8")

    def test_coordinate_layer_is_optional_and_read_only(self):
        self.assertIn('id="coordinateToggleBtn"', self.html)
        self.assertIn('id="coordinateModeBtn"', self.html)
        self.assertIn('aria-pressed="false"', self.html)
        self.assertIn("coordinateOverlayEnabled = false", self.game_js)
        self.assertIn("只读辅助层", self.game_js)
        self.assertIn("showAIAnalysisOverlay", self.game_js)
        self.assertIn("configureHighDpiCanvas", self.game_js)
        self.assertIn("devicePixelRatio", self.game_js)
        self.assertNotIn("gameState =", self.game_js[self.game_js.index("function showAIAnalysisOverlay"):self.game_js.index("function clearAIAnalysisOverlay")])

    def test_ai_overlay_has_clear_control_and_read_only_legend(self):
        self.assertIn('id="clearAiOverlayBtn"', self.html)
        self.assertIn('id="aiCandidateDock"', self.html)
        self.assertIn('id="aiCandidateDetail"', self.html)
        self.assertIn("仅显示，不会自动落子", self.html)
        self.assertIn("onOverlayGameStateChanged", self.game_js)
        self.assertIn("selectAIAnalysisCandidate", self.game_js)
        self.assertIn("drawSelectedCandidate", self.game_js)

    def test_markdown_is_rendered_by_safe_formatter(self):
        self.assertIn("ChatFormat.renderMarkdown", self.chat_js)
        self.assertIn("escapeHtml", self.format_js)
        self.assertIn("<strong>", self.format_js)
        self.assertIn("<h", self.format_js)
        self.assertIn("coordinate-chip", self.chat_js)
        self.assertIn("chat-candidate-card", self.chat_js)
        self.assertIn("查看首选路径", self.chat_js)

    def test_explainable_coach_cards_are_rendered(self):
        self.assertIn("renderCoachReport", self.chat_js)
        self.assertIn("coach-feature-grid", self.css)
        self.assertIn("coach-counterfactual", self.css)
        self.assertIn("非私有思维链", self.chat_js)

    def test_original_canvas_size_and_core_layout_remain(self):
        self.assertIn("canvasW = 820;", self.game_js)
        self.assertIn("canvasH = 760;", self.game_js)
        self.assertIn("canvas.style.width = '100%'", self.game_js)
        self.assertIn('.panel {\n  width: 240px;', self.css)
        self.assertIn('id="setupCard"', self.html)


if __name__ == "__main__":
    unittest.main()
