from __future__ import annotations

import unittest

from board import BoardState
from game_tools import (
    MCP_TOOL_NAMES,
    evaluate_move,
    evaluate_position,
    get_board_geometry,
    get_legal_moves,
    rank_candidate_moves,
    recommend_move,
    simulate_moves,
)


class GameToolsTestCase(unittest.TestCase):
    def setUp(self):
        self.state = BoardState.new_game(2)
        self.game = {
            "game_id": "tool-test",
            "state": self.state,
            "mode": "pve",
            "difficulty": 2,
            "save_name": "",
        }

    def test_mcp_contract_covers_data_and_calculation_interfaces(self):
        expected = {
            "list_games", "get_game_state", "get_move_history", "get_ai_decisions",
            "get_evaluation_snapshots", "get_chat_history", "get_tool_audit_logs",
            "list_replays", "get_replay", "get_board_geometry", "get_legal_moves",
            "evaluate_position", "evaluate_move", "rank_candidate_moves",
            "recommend_move", "simulate_moves", "get_game_statistics",
        }
        self.assertTrue(expected.issubset(set(MCP_TOOL_NAMES)))

    def test_legal_evaluation_ranking_and_recommendation_are_consistent(self):
        legal = get_legal_moves(self.game)
        self.assertGreater(legal["count"], 0)
        first = legal["moves"][0]

        evaluated = evaluate_move(self.game, first["from"], first["to"])
        self.assertIn("score_delta", evaluated)
        self.assertEqual(evaluated["move_detail"]["path"][0], first["from"])
        self.assertEqual(evaluated["move_detail"]["path"][-1], first["to"])
        self.assertIn("components", evaluate_position(self.game))

        ranked = rank_candidate_moves(self.game, limit=5)
        self.assertLessEqual(ranked["count"], 5)
        recommendation = recommend_move(self.game, difficulty=2)
        self.assertIn(recommendation["move"], legal["moves"])
        self.assertGreaterEqual(len(recommendation["candidate_details"]), 1)
        for candidate in recommendation["candidate_details"]:
            self.assertEqual(candidate["path"][0], candidate["move"]["from"])
            self.assertEqual(candidate["path"][-1], candidate["move"]["to"])
            self.assertIn(candidate["move_type"], {"step", "jump", "unknown"})

    def test_simulation_is_read_only(self):
        first = get_legal_moves(self.game)["moves"][0]
        result = simulate_moves(self.game, [first])
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"]["move_count"], 1)
        self.assertEqual(result["trace"][0]["move_detail"]["path"][0], first["from"])
        self.assertEqual(result["trace"][0]["move_detail"]["path"][-1], first["to"])
        self.assertEqual(self.state.to_dict()["move_count"], 0)

    def test_multi_jump_path_identifies_piece_landings_and_jump_over_points(self):
        state = BoardState([0, 3])
        for position, player_id in [((4, 4), 0), ((4, 5), 3), ((4, 7), 3)]:
            state.board[position[0]][position[1]] = player_id + 1
            state._pieces[player_id].add(position)
        state.current_player = 0
        for player_id in state.active_players:
            state._update_score(player_id)
        game = {"game_id": "path-test", "state": state, "mode": "pve", "difficulty": 2}

        detail = evaluate_move(game, [4, 4], [4, 8])["move_detail"]
        self.assertEqual(detail["piece"]["position"], [4, 4])
        self.assertEqual(detail["target"], [4, 8])
        self.assertEqual(detail["path"], [[4, 4], [4, 6], [4, 8]])
        self.assertEqual(detail["jumped_over"], [[4, 5], [4, 7]])
        self.assertEqual(detail["jump_count"], 2)
        self.assertEqual(detail["move_type"], "jump")

    def test_geometry_matches_existing_board(self):
        geometry = get_board_geometry()
        self.assertEqual(geometry["rows"], 17)
        self.assertEqual(geometry["cols"], 17)
        self.assertEqual(len(geometry["valid_holes"]), 121)
        self.assertEqual(geometry["coordinate_system"]["format"], "[row, col]")
        self.assertIn("row 0", geometry["coordinate_system"]["screen_orientation"])


if __name__ == "__main__":
    unittest.main()
