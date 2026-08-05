from __future__ import annotations

import ast
from pathlib import Path
import unittest


class StreamJsonDependencyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_path = Path(__file__).resolve().parents[1] / "app.py"
        cls.source = cls.app_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(cls.app_path))

    def test_json_module_is_imported(self):
        imported = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                imported.update(alias.asname or alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.update(alias.asname or alias.name for alias in node.names)
        self.assertIn(
            "json",
            imported,
            "app.py calls json.dumps in the SSE generator but does not import json",
        )

    def test_stream_generator_uses_json_dumps(self):
        calls = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "json"
                and func.attr == "dumps"
            ):
                calls.append(node)
        self.assertGreaterEqual(
            len(calls),
            1,
            "The SSE endpoint must serialize events through json.dumps",
        )

    def test_stream_route_keeps_sse_contract(self):
        self.assertIn('/api/chat/stream', self.source)
        self.assertIn('text/event-stream', self.source)
        self.assertIn('yield f"data: {payload_text}\\n\\n"', self.source)


if __name__ == "__main__":
    unittest.main()
