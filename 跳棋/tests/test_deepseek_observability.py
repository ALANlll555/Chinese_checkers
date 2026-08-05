from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from board import BoardState
from database import GameDatabase
from deepseek_chat import DeepSeekChatService


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class DeepSeekObservabilityTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        self.db = GameDatabase(
            Path(self.temp.name) / "observability.sqlite3",
            root / "schema.sql",
        )
        state = BoardState.new_game(2)
        self.game = {
            "game_id": "observability",
            "state": state,
            "mode": "pve",
            "difficulty": 2,
            "api_key": "test-key",
            "deepseek_settings": {
                "base_url": "https://example.invalid",
                "model": "custom-model",
                "thinking": True,
                "show_reasoning": True,
                "context_1m": True,
                "strict_tools": True,
                "reasoning_effort": "max",
                "max_tokens": 2048,
            },
        }
        self.db.create_game(
            "observability", state.to_dict(), "pve", 2, 2, True, ""
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_request_uses_game_level_settings(self):
        captured = {}

        def post(url, **kwargs):
            captured["url"] = url
            captured["payload"] = kwargs["json"]
            return FakeResponse({
                "choices": [{"message": {
                    "content": "完成",
                    "reasoning_content": "已核对规则。",
                }}]
            })

        service = DeepSeekChatService(self.db, http_post=post)
        result = service.reply(self.game, "分析")

        self.assertEqual(captured["payload"]["model"], "custom-model")
        self.assertEqual(captured["payload"]["max_tokens"], 2048)
        self.assertEqual(captured["payload"]["reasoning_effort"], "max")
        self.assertIn("/beta/chat/completions", captured["url"])
        self.assertEqual(result["model"], "custom-model")
        self.assertGreaterEqual(result["elapsed_seconds"], 0)
        self.assertGreaterEqual(result["reasoning_seconds"], 0)

    def test_tool_trace_contains_arguments_result_and_duration(self):
        responses = iter([
            FakeResponse({"choices": [{"message": {
                "content": "",
                "reasoning_content": "先读取局面。",
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "get_game_state",
                        "arguments": "{}",
                    },
                }],
            }}]}),
            FakeResponse({"choices": [{"message": {
                "content": "分析完成。",
                "reasoning_content": "工具结果已核对。",
            }}]}),
        ])

        service = DeepSeekChatService(
            self.db, http_post=lambda *args, **kwargs: next(responses)
        )
        result = service.reply(self.game, "分析当前局面")
        trace = result["tool_trace"]

        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["name"], "get_game_state")
        self.assertEqual(trace[0]["arguments"], {})
        self.assertIn("result_preview", trace[0])
        self.assertIn("duration_ms", trace[0])
        self.assertEqual(trace[0]["source"], "mcp-shared-tool-registry")

        history = self.db.get_chat_history("observability")
        self.assertEqual(
            history[-1]["metadata"]["tool_trace"][0]["name"],
            "get_game_state",
        )


if __name__ == "__main__":
    unittest.main()
