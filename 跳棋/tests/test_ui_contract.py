from __future__ import annotations

import unittest
from pathlib import Path


class UIContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.html = (root / "templates" / "index.html").read_text(encoding="utf-8")
        cls.css = (root / "static" / "css" / "style.css").read_text(encoding="utf-8")
        cls.game_js = (root / "static" / "js" / "game.js").read_text(encoding="utf-8")

    def test_left_chat_panel_is_added_without_replacing_board_or_right_panel(self):
        self.assertIn('class="panel chat-panel"', self.html)
        self.assertIn('id="boardCanvas"', self.html)
        self.assertIn('id="setupCard"', self.html)
        self.assertIn('/static/js/chat.js?v=17', self.html)

    def test_sidebars_share_the_same_panel_width(self):
        self.assertIn('.panel {\n  width: 240px;', self.css)
        self.assertNotIn('.chat-panel {\n  width:', self.css)

    def test_board_canvas_is_larger_but_bounded(self):
        self.assertIn('canvasW = 820;', self.game_js)
        self.assertIn('canvasH = 760;', self.game_js)
        self.assertIn('width: min(820px, calc(100vw - 540px));', self.css)


if __name__ == "__main__":
    unittest.main()
