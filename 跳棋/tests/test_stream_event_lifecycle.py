from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


class StreamEventLifecycleTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        self.db = GameDatabase(
            Path(self.temp.name) / "stream.sqlite3",
            root / "schema.sql",
        )
        state = BoardState.new_game(2)
        self.game = {
            "game_id": "stream-events",
            "state": state,
            "mode": "pve",
            "difficulty": 2,
            "api_key": "test-key",
            "deepseek_settings": {
                "thinking": True,
                "show_reasoning": True,
                "context_1m": True,
            },
        }
        self.db.create_game(
            "stream-events", state.to_dict(), "pve", 2, 2, True, ""
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_reasoning_and_tool_events_precede_final_answer(self):
        responses = iter([
            FakeResponse({
                "choices": [{"message": {
                    "content": "",
                    "reasoning_content": "先读取当前棋盘事实。",
                    "tool_calls": [{
                        "id": "call-state",
                        "type": "function",
                        "function": {
                            "name": "get_game_state",
                            "arguments": "{}",
                        },
                    }],
                }}]
            }),
            FakeResponse({
                "choices": [{"message": {
                    "content": "建议优先建立中路跳板。",
                    "reasoning_content": "工具结果支持该结论。",
                }}]
            }),
        ])

        events = []
        service = DeepSeekChatService(
            self.db,
            http_post=lambda *args, **kwargs: next(responses),
        )
        result = service.reply(
            self.game,
            "分析当前局面",
            event_callback=events.append,
        )

        event_types = [event["type"] for event in events]
        self.assertEqual(event_types[0], "start")
        self.assertIn("reasoning", event_types)
        self.assertIn("tool_start", event_types)
        self.assertIn("tool_end", event_types)
        self.assertEqual(event_types[-2:], ["text", "done"])

        reasoning_index = event_types.index("reasoning")
        tool_start_index = event_types.index("tool_start")
        tool_end_index = event_types.index("tool_end")
        text_index = event_types.index("text")
        self.assertLess(reasoning_index, tool_start_index)
        self.assertLess(tool_start_index, tool_end_index)
        self.assertLess(tool_end_index, text_index)

        tool_start = events[tool_start_index]
        tool_end = events[tool_end_index]
        self.assertEqual(tool_start["name"], "get_game_state")
        self.assertEqual(tool_start["arguments"], {})
        self.assertTrue(tool_end["success"])
        self.assertIn("result_preview", tool_end)

        self.assertEqual(events[-1]["result"]["answer"], result["answer"])

    def test_callback_failure_cannot_break_reply(self):
        response = FakeResponse({
            "choices": [{"message": {
                "content": "回答完成。",
                "reasoning_content": "已验证。",
            }}]
        })
        service = DeepSeekChatService(
            self.db,
            http_post=lambda *args, **kwargs: response,
        )

        def broken_callback(_event):
            raise RuntimeError("UI disconnected")

        result = service.reply(
            self.game,
            "分析",
            event_callback=broken_callback,
        )
        self.assertTrue(result["answer"])


if __name__ == "__main__":
    unittest.main()
