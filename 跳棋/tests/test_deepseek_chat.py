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


class DeepSeekChatTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        self.db = GameDatabase(Path(self.temp.name) / "chat.sqlite3", root / "schema.sql")
        state = BoardState.new_game(2)
        self.game = {
            "game_id": "chat-test",
            "state": state,
            "mode": "pve",
            "difficulty": 2,
            "save_name": "",
            "api_key": "test-key",
        }
        self.db.create_game("chat-test", state.to_dict(), "pve", 2, 2, True, "")

    def tearDown(self):
        self.temp.cleanup()

    def test_tool_call_round_trip_is_persisted(self):
        responses = iter([
            FakeResponse({
                "choices": [{"message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "get_game_state", "arguments": "{}"},
                    }],
                }}]
            }),
            FakeResponse({
                "choices": [{"message": {"content": "当前应优先建立向前梯子。"}}]
            }),
        ])

        service = DeepSeekChatService(self.db, http_post=lambda *args, **kwargs: next(responses))
        result = service.reply(self.game, "分析当前局面")

        self.assertEqual(result["answer"], "当前应优先建立向前梯子。")
        self.assertEqual(len(result["tool_trace"]), 1)
        history = self.db.get_chat_history("chat-test")
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])
        self.assertEqual(self.db.get_statistics("chat-test")["tool_call_count"], 1)

    def test_missing_key_degrades_without_network(self):
        self.game["api_key"] = ""
        service = DeepSeekChatService(self.db, http_post=lambda *args, **kwargs: self.fail("network called"))
        result = service.reply(self.game, "推荐一步")
        self.assertFalse(result["configured"])
        self.assertEqual(result["coach_mode"], "local")
        self.assertIn("可验证证据", result["answer"])
        self.assertTrue(result["coach_report"]["candidates"])


if __name__ == "__main__":
    unittest.main()
