from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


class FullFlowSelfTestContractCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        path = root / "release_selftest.py"
        spec = importlib.util.spec_from_file_location("release_selftest_under_test", path)
        cls.module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.module)
        cls.source = path.read_text(encoding="utf-8")
        cls.launcher = (root.parent / "launcher.py").read_text(encoding="utf-8")

    def test_all_inline_controls_resolve_to_javascript(self):
        result = self.module.static_button_audit()
        self.assertGreaterEqual(result["inline_handlers"], 30)
        self.assertGreaterEqual(result["unique_handlers"], 20)

    def test_runtime_selftest_covers_backend_button_routes(self):
        for route in (
            "/api/new_game",
            "/api/legal_moves",
            "/api/move",
            "/api/ai_move",
            "/api/undo",
            "/api/hint",
            "/api/comment",
            "/api/chat/stream",
            "/api/chat/history",
            "/api/chat/clear",
            "/api/deepseek/test",
            "/api/mcp/manifest",
            "/api/load_replay/",
            "/api/archive/",
        ):
            self.assertIn(route, self.source)

    def test_launcher_runs_cached_selftest_after_dependencies(self):
        dependency_index = self.launcher.index(
            'run([str(python), str(PROJECT / "bootstrap.py")])'
        )
        selftest_index = self.launcher.index(
            'run([str(python), str(PROJECT / "release_selftest.py")])'
        )
        game_index = self.launcher.index(
            'return run([str(python), str(PROJECT / "launch_game.py")])'
        )
        self.assertLess(dependency_index, selftest_index)
        self.assertLess(selftest_index, game_index)
        self.assertIn("already passed for this build; skipping", self.source)


if __name__ == "__main__":
    unittest.main()
