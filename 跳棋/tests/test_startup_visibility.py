from __future__ import annotations

from pathlib import Path
import unittest


class StartupVisibilityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = Path(__file__).resolve().parents[1]
        cls.root = cls.project.parent
        cls.bat_bytes = (cls.root / "启动游戏.bat").read_bytes()
        cls.bat = cls.bat_bytes.decode("ascii")
        cls.launcher = (cls.root / "launcher.py").read_text(encoding="utf-8")
        cls.game_launcher = (cls.project / "launch_game.py").read_text(encoding="utf-8")
        cls.bootstrap = (cls.project / "bootstrap.py").read_text(encoding="utf-8")

    def test_batch_has_no_bom_and_always_pauses(self):
        self.assertFalse(self.bat_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertIn(":finished", self.bat)
        self.assertIn("pause", self.bat.lower())
        self.assertIn("startup.log", self.bat)

    def test_running_inside_zip_is_detected(self):
        self.assertIn("Please extract the complete ZIP package", self.bat)
        self.assertIn("was not fully extracted", self.launcher)

    def test_game_survives_optional_mcp_failure(self):
        self.assertIn("_start_mcp_best_effort", self.game_launcher)
        self.assertIn('return "failed"', self.game_launcher)
        self.assertIn("from app import app", self.game_launcher)

    def test_bootstrap_checks_versions_and_keeps_optional_fallback(self):
        self.assertIn("metadata.version", self.bootstrap)
        self.assertIn("skipping pip download", self.bootstrap)
        self.assertIn("Optional MCP HTTP dependencies remain unavailable", self.bootstrap)


if __name__ == "__main__":
    unittest.main()
