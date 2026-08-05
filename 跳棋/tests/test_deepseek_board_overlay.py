from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from board import BoardState
from database import GameDatabase
from deepseek_chat import DeepSeekChatService
from game_tools import recommend_move


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class DeepSeekBoardOverlayTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        self.db = GameDatabase(Path(self.temp.name) / "overlay.sqlite3", root / "schema.sql")
        state = BoardState.new_game(2)
        self.game = {
            "game_id": "overlay-test",
            "state": state,
            "mode": "pve",
            "difficulty": 2,
            "save_name": "",
            "api_key": "test-key",
        }
        self.db.create_game("overlay-test", state.to_dict(), "pve", 2, 2, True, "")

    def tearDown(self):
        self.temp.cleanup()

    def test_recommendation_returns_structured_read_only_overlay(self):
        move = sorted(self.game["state"].get_valid_moves())[0]
        responses = iter([
            FakeResponse({"choices": [{"message": {
                "content": None,
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "recommend_move", "arguments": "{}"},
                }],
            }}]}),
            FakeResponse({"choices": [{"message": {
                "content": f"建议走 **({move[0][0]},{move[0][1]}) → ({move[1][0]},{move[1][1]})**。"
            }}]}),
        ])
        result_payload = recommend_move(self.game, difficulty=2)

        with patch("deepseek_chat.execute_chat_tool", return_value=result_payload):
            service = DeepSeekChatService(
                self.db, http_post=lambda *args, **kwargs: next(responses)
            )
            result = service.reply(self.game, "推荐一步")

        overlay = result["board_overlay"]
        self.assertTrue(overlay["read_only"])
        self.assertEqual(overlay["moves"][0]["from"], result_payload["candidate_details"][0]["move"]["from"])
        self.assertEqual(overlay["moves"][0]["to"], result_payload["candidate_details"][0]["move"]["to"])
        self.assertTrue(overlay["moves"][0]["verified"])
        self.assertEqual(overlay["moves"][0]["path"][0], overlay["moves"][0]["from"])
        self.assertEqual(overlay["moves"][0]["path"][-1], overlay["moves"][0]["to"])
        self.assertIn(overlay["moves"][0]["move_type"], {"step", "jump", "unknown"})
        self.assertIn("path_text", overlay["moves"][0])

    def test_text_coordinate_fallback_is_bounded(self):
        move = sorted(self.game["state"].get_valid_moves())[0]
        response = FakeResponse({"choices": [{"message": {
            "content": f"可考虑（{move[0][0]},{move[0][1]}）→（{move[1][0]},{move[1][1]}）。"
        }}]})
        service = DeepSeekChatService(
            self.db, http_post=lambda *args, **kwargs: response
        )
        result = service.reply(self.game, "给出坐标")
        self.assertIsNone(result["board_overlay"])
        self.assertIn("（", result["answer"])


if __name__ == "__main__":
    unittest.main()
