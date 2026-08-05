from __future__ import annotations

import ast
from pathlib import Path
import unittest

import config
import launch_game


class OneClickReleaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = Path(__file__).resolve().parents[1]
        cls.root = cls.project.parent
        cls.launcher_bytes = (cls.root / "启动游戏.bat").read_bytes()
        cls.launcher = cls.launcher_bytes.decode("ascii")
        cls.root_launcher = (cls.root / "launcher.py").read_text(encoding="utf-8")
        cls.mcp_source = (cls.project / "mcp_server.py").read_text(
            encoding="utf-8"
        )

    def test_single_windows_entry_point(self):
        self.assertTrue((self.root / "启动游戏.bat").exists())
        self.assertFalse((self.root / "启动跳棋.bat").exists())
        self.assertFalse((self.root / "启动MCP.bat").exists())
        self.assertEqual(
            sorted(path.name for path in self.root.glob("*.bat")),
            ["启动游戏.bat"],
        )

    def test_launcher_prepares_venv_and_runs_orchestrator(self):
        self.assertFalse(self.launcher_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertIn("launcher.py", self.launcher)
        self.assertIn("pause", self.launcher.lower())
        self.assertIn(".venv", self.root_launcher)
        self.assertIn("bootstrap.py", self.root_launcher)
        self.assertIn("launch_game.py", self.root_launcher)
        self.assertIn("release_selftest.py", self.root_launcher)
        self.assertIn("startup.log", self.root_launcher)

    def test_release_endpoints_are_loopback_only(self):
        self.assertEqual(config.APP_HOST, "127.0.0.1")
        self.assertEqual(config.MCP_HOST, "127.0.0.1")
        self.assertEqual(config.APP_PORT, 5000)
        self.assertEqual(config.MCP_PORT, 8765)
        self.assertTrue(config.MCP_URL.endswith("/mcp"))

    def test_orchestrator_is_importable_and_process_safe(self):
        self.assertTrue(callable(launch_game._port_is_open))
        self.assertTrue(callable(launch_game._wait_for_port))
        source = (self.project / "launch_game.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("subprocess.Popen", source)
        self.assertIn("webbrowser.open", source)
        self.assertIn("_stop_mcp", source)
        self.assertIn("use_reloader=False", source)

    def test_mcp_server_uses_configured_http_binding(self):
        self.assertIn("mcp.streamable_http_app()", self.mcp_source)
        self.assertIn("host=cfg.MCP_HOST", self.mcp_source)
        self.assertIn("port=cfg.MCP_PORT", self.mcp_source)
        self.assertIn("uvicorn.run", self.mcp_source)

    def test_mcp_failure_does_not_abort_game(self):
        source = (self.project / "launch_game.py").read_text(encoding="utf-8")
        self.assertIn("_start_mcp_best_effort", source)
        self.assertIn("The game will continue", source)
        self.assertNotIn("_mcp_process = _start_mcp()", source)


if __name__ == "__main__":
    unittest.main()
