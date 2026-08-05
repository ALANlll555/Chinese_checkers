from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai import evaluate_components
from board import BoardState
from database import GameDatabase


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        self.db = GameDatabase(Path(self.temp.name) / "test.sqlite3", root / "schema.sql")
        self.state = BoardState.new_game(2)
        self.game_id = "db-test"
        self.db.create_game(
            self.game_id, self.state.to_dict(), "pve", 2, 2, True, ""
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_game_move_ai_evaluation_and_undo_are_persisted(self):
        move = sorted(self.state.get_valid_moves())[0]
        before = self.state.to_dict()
        player_id = self.state.current_player
        after_state = self.state.apply_move(move)
        after = after_state.to_dict()
        before_eval = evaluate_components(self.state, player_id)
        after_eval = evaluate_components(after_state, player_id)

        self.db.record_move(
            self.game_id, 1, player_id, "ai", move, before, after,
            before_eval["score"], after_eval["score"],
        )
        self.db.record_ai_decision(
            self.game_id, 1, player_id, 2,
            {"from": list(move[0]), "to": list(move[1])},
            [{"from": list(move[0]), "to": list(move[1])}], 12.5,
        )
        self.db.record_evaluation(self.game_id, 1, player_id, "after", after_eval)

        self.assertEqual(len(self.db.get_moves(self.game_id)), 1)
        self.assertEqual(len(self.db.get_ai_decisions(self.game_id)), 1)
        self.assertEqual(len(self.db.get_evaluation_snapshots(self.game_id)), 1)
        self.assertEqual(self.db.get_game(self.game_id)["state"]["move_count"], 1)

        self.db.undo_moves(self.game_id, 0, before)
        self.assertEqual(self.db.get_moves(self.game_id), [])
        self.assertEqual(self.db.get_game(self.game_id)["state"]["move_count"], 0)

    def test_chat_and_tool_audit_are_queryable(self):
        self.db.append_chat_message(self.game_id, "user", "分析局面")
        self.db.append_chat_message(self.game_id, "assistant", "正在分析", model="test")
        self.db.log_tool_call(
            self.game_id, "mcp", "get_game_state", {}, {"ok": True}, True, 1.2
        )

        history = self.db.get_chat_history(self.game_id)
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])
        stats = self.db.get_statistics(self.game_id)
        self.assertEqual(stats["chat_message_count"], 2)
        self.assertEqual(stats["tool_call_count"], 1)
        self.assertEqual(self.db.get_tool_logs(self.game_id)[0]["operation"], "get_game_state")


if __name__ == "__main__":
    unittest.main()
