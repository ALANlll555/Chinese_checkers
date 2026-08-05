from pathlib import Path
import unittest


class OverlayGuardContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.guard = (root / "static/js/overlay_guard.js").read_text(encoding="utf-8")
        cls.game = (root / "static/js/game.js").read_text(encoding="utf-8")
        cls.chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
        cls.html = (root / "templates/index.html").read_text(encoding="utf-8")

    def test_overlay_guard_is_loaded_before_game(self):
        self.assertLess(self.html.index("overlay_guard.js"), self.html.index("game.js?v=12"))

    def test_frontend_requires_verified_owned_source_and_empty_target(self):
        for token in ("verified", "source_owned", "target_empty", "stale-state-token"):
            self.assertIn(token, self.guard)

    def test_first_candidate_is_selected_immediately(self):
        self.assertIn("selectedIndex: 0", self.game)
        self.assertIn("首选路径已显示", self.game)
        self.assertIn("selectedIndex = 0", self.chat)

    def test_target_ring_is_always_at_hole_center(self):
        self.assertIn("x: target.x", self.game)
        self.assertIn("y: target.y", self.game)
        self.assertIn("ctx.arc(marker.target.x, marker.target.y", self.game)


if __name__ == "__main__": unittest.main()
