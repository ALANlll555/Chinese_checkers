from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from board import BoardState
from database import GameDatabase
from deepseek_chat import DeepSeekChatService, _append_overlay_move, _new_overlay
from game_tools import explain_position, recommend_move, validate_candidate_move


class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): return None
    def json(self): return self.payload


class RecommendationInvariantTestCase(unittest.TestCase):
    def setUp(self):
        self.state = BoardState.new_game(2)
        self.game = {
            "game_id": "invariant-test", "state": self.state, "mode": "pve",
            "difficulty": 2, "save_name": "", "api_key": "test-key",
        }

    def test_first_turn_candidates_are_real_human_pieces(self):
        for current in (0, 3):
            self.state.current_player = current
            report = explain_position(self.game, limit=5)
            self.assertEqual(report["player_id"], 0)
            for candidate in report["candidates"]:
                move = candidate["move"]
                source = tuple(move["from"]); target = tuple(move["to"])
                self.assertEqual(self.state.get_piece(source), 1)
                self.assertEqual(self.state.get_piece(target), 0)
                checked = validate_candidate_move(self.game, source, target, 3)
                self.assertTrue(checked["valid"])
                self.assertEqual(checked["player_id"], 0)

    def test_empty_source_and_opponent_move_are_rejected(self):
        overlay = _new_overlay(self.game, 0)
        opponent_move = sorted(self.state.get_valid_moves(3))[0]
        accepted = _append_overlay_move(
            overlay, {"from": list(opponent_move[0]), "to": list(opponent_move[1])},
            label="bad", kind="candidate", game=self.game, expected_player_id=0,
        )
        self.assertFalse(accepted)
        self.assertEqual(overlay["moves"], [])
        self.assertGreaterEqual(len(overlay["rejected"]), 1)

    def test_coach_recommendation_is_deterministic_and_verified(self):
        first = recommend_move(self.game)
        second = recommend_move(self.game)
        self.assertEqual(first["move"], second["move"])
        self.assertEqual(first["selection_policy"], "deterministic-explainable-ranking")
        self.assertTrue(all(item["verified"] for item in first["candidate_details"]))

    def test_deepseek_cannot_override_human_player_or_visual_overlay(self):
        temp = tempfile.TemporaryDirectory()
        try:
            root = Path(__file__).resolve().parents[1]
            db = GameDatabase(Path(temp.name) / "db.sqlite3", root / "schema.sql")
            db.create_game("invariant-test", self.state.to_dict(), "pve", 2, 2, True, "")
            responses = iter([
                FakeResponse({"choices":[{"message":{
                    "content":None, "tool_calls":[{
                        "id":"call-1", "type":"function",
                        "function":{"name":"recommend_move", "arguments":"{\"player_id\":3}"},
                    }]
                }}]}),
                FakeResponse({"choices":[{"message":{
                    "content":"建议（13,7）→（12,7），但以规则报告为准。"
                }}]}),
            ])
            captured = []
            def fake_tool(name, args, game):
                captured.append(dict(args))
                return recommend_move(game, player_id=args.get("player_id"))
            with patch("deepseek_chat.execute_chat_tool", side_effect=fake_tool):
                result = DeepSeekChatService(db, http_post=lambda *a, **k: next(responses)).reply(
                    self.game, "第一步推荐"
                )
            self.assertEqual(captured[0]["player_id"], 0)
            overlay = result["board_overlay"]
            self.assertEqual(overlay["player_id"], 0)
            self.assertEqual(self.state.get_piece(tuple(overlay["moves"][0]["from"])), 1)
            self.assertTrue(overlay["moves"][0]["verified"])
            self.assertTrue(result["coach_guard"]["model_move_rejected"])
            self.assertNotIn("(13,7)", result["answer"].replace("（", "(").replace("）", ")"))
        finally:
            temp.cleanup()

    def test_state_change_during_deepseek_call_refreshes_report(self):
        temp = tempfile.TemporaryDirectory()
        try:
            root = Path(__file__).resolve().parents[1]
            db = GameDatabase(Path(temp.name) / "db.sqlite3", root / "schema.sql")
            db.create_game("invariant-test", self.state.to_dict(), "pve", 2, 2, True, "")
            changed = {"done": False}
            def post(*args, **kwargs):
                if not changed["done"]:
                    move = sorted(self.game["state"].get_valid_moves())[0]
                    self.game["state"] = self.game["state"].apply_move(move)
                    changed["done"] = True
                return FakeResponse({"choices":[{"message":{"content":"原局面建议（2,7）→（4,8）。"}}]})
            result = DeepSeekChatService(db, http_post=post).reply(self.game, "分析当前局面")
            self.assertTrue(result["coach_guard"]["state_refreshed"])
            self.assertEqual(result["coach_report"]["move_count"], 1)
            self.assertEqual(result["board_overlay"]["move_count"], 1)
            self.assertIn("棋局发生了变化", result["answer"])
        finally:
            temp.cleanup()


if __name__ == "__main__": unittest.main()
