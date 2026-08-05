from __future__ import annotations

from pathlib import Path
import unittest


class DeepSeekOfficialProtocolContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.source = (root / "deepseek_chat.py").read_text(encoding="utf-8")

    def test_upstream_request_enables_sse_and_usage(self):
        self.assertIn('payload["stream"] = True', self.source)
        self.assertIn(
            'payload["stream_options"] = {"include_usage": True}',
            self.source,
        )
        self.assertIn('response.iter_lines(', self.source)
        self.assertIn('data_text == "[DONE]"', self.source)

    def test_stream_parser_accumulates_all_official_delta_fields(self):
        self.assertIn('delta.get("reasoning_content")', self.source)
        self.assertIn('delta.get("content")', self.source)
        self.assertIn('delta.get("tool_calls")', self.source)

    def test_tool_call_history_preserves_reasoning_content(self):
        self.assertIn(
            '"agent_messages": agent_messages or []',
            self.source,
        )
        self.assertIn(
            '"tool_reasoning_history_enabled": True',
            self.source,
        )
        self.assertIn(
            'assistant_tool_message["reasoning_content"]',
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
