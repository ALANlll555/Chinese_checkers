from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import importlib.util
import unittest


class DependencyBootstrapSkipTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "bootstrap.py"
        spec = importlib.util.spec_from_file_location("bootstrap_under_test", path)
        cls.module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.module)

    @staticmethod
    def ready_status():
        return [
            {
                "distribution": "flask",
                "normalized": "flask",
                "specifier": ">=2.3,<4",
                "requirement": "flask>=2.3,<4",
                "module": "flask",
                "optional": False,
                "installed_version": "3.1.0",
                "module_ready": True,
                "satisfied": True,
            },
            {
                "distribution": "mcp",
                "normalized": "mcp",
                "specifier": ">=1.27,<2",
                "requirement": "mcp>=1.27,<2",
                "module": "mcp",
                "optional": True,
                "installed_version": "1.30.0",
                "module_ready": True,
                "satisfied": True,
            },
        ]

    def test_ready_versions_never_call_pip(self):
        with (
            patch.object(self.module, "requirement_status", return_value=self.ready_status()),
            patch.object(self.module, "pip_install") as pip_install,
            patch.object(self.module, "write_marker"),
            patch.object(self.module, "read_marker", return_value={}),
        ):
            self.assertEqual(self.module.main([]), 0)
            pip_install.assert_not_called()

    def test_requirement_change_does_not_download_when_versions_still_match(self):
        with (
            patch.object(self.module, "requirement_status", return_value=self.ready_status()),
            patch.object(self.module, "pip_install") as pip_install,
            patch.object(self.module, "write_marker"),
            patch.object(
                self.module,
                "read_marker",
                return_value={"requirements_sha256": "old-build"},
            ),
        ):
            self.assertEqual(self.module.main([]), 0)
            pip_install.assert_not_called()

    def test_previous_optional_failure_has_download_backoff(self):
        status = self.ready_status()
        status[-1] = {
            **status[-1],
            "installed_version": None,
            "module_ready": False,
            "satisfied": False,
        }
        with (
            patch.object(self.module, "requirement_status", return_value=status),
            patch.object(self.module, "digest", return_value="same"),
            patch.object(self.module, "pip_install") as pip_install,
            patch.object(self.module, "write_marker"),
            patch.object(
                self.module,
                "read_marker",
                return_value={
                    "requirements_sha256": "same",
                    "optional_failures": ["mcp>=1.27,<2"],
                    "install_attempted": True,
                },
            ),
        ):
            self.assertEqual(self.module.main([]), 0)
            pip_install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
