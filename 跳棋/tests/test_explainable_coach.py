from __future__ import annotations

import unittest

from board import BoardState
from game_tools import execute_chat_tool, explain_last_move, explain_position


class ExplainableCoachTestCase(unittest.TestCase):
    def setUp(self):
        self.state = BoardState.new_game(2)
        self.game = {
            "game_id": "xai-test",
            "state": self.state,
            "mode": "pve",
            "difficulty": 2,
        }

    def test_report_contains_evidence_candidates_and_counterfactual(self):
        report = explain_position(self.game, limit=5)
        self.assertEqual(report["report_version"], "xai-coach-2")
        self.assertEqual(report["player_id"], 0)
        self.assertEqual(len(report["current"]["features"]), 5)
        self.assertGreaterEqual(len(report["candidates"]), 2)
        first = report["candidates"][0]
        self.assertIn("feature_changes", first)
        self.assertIn("reason", first)
        self.assertIn("tradeoff", first)
        self.assertEqual(len(first["feature_changes"]), 5)
        self.assertIn("confidence", report)
        self.assertIn("evidence", report)
        self.assertTrue(report["evidence"]["all_candidates_verified"])
        for candidate in report["candidates"]:
            source = tuple(candidate["move"]["from"])
            target = tuple(candidate["move"]["to"])
            self.assertEqual(self.state.get_piece(source), 1)
            self.assertEqual(self.state.get_piece(target), 0)
            self.assertTrue(candidate["verified"])

    def test_pve_tool_defaults_to_human_perspective(self):
        self.state.current_player = 3
        result = execute_chat_tool("explain_position", {}, self.game)
        self.assertEqual(result["player_id"], 0)

    def test_last_move_explanation_compares_before_and_after(self):
        move = sorted(self.state.get_valid_moves())[0]
        self.game["state"] = self.state.apply_move(move)
        report = explain_last_move(self.game)
        self.assertTrue(report["available"])
        self.assertEqual(len(report["feature_changes"]), 5)
        self.assertEqual(report["move"]["from"], list(move[0]))
        self.assertEqual(report["move"]["to"], list(move[1]))


if __name__ == "__main__":
    unittest.main()
