from __future__ import annotations

import random
import unittest

from board import BoardState
from game_tools import _move_path, _state_for_player, validate_candidate_move


class RecommendationPropertyAuditTestCase(unittest.TestCase):
    def test_random_states_keep_source_target_and_path_invariants(self):
        checked = 0
        for player_count in (2, 3, 4, 6):
            for seed in range(3):
                rng = random.Random(player_count * 100 + seed)
                state = BoardState.new_game(player_count)
                game = {
                    "game_id": "property",
                    "state": state,
                    "mode": "pvp",
                    "difficulty": 2,
                }
                for _ in range(12):
                    for pid in state.active_players:
                        view = _state_for_player(state, pid)
                        for move in view.get_valid_moves():
                            checked += 1
                            validation = validate_candidate_move(
                                game, move[0], move[1], pid
                            )
                            self.assertTrue(validation["valid"])
                            path = _move_path(view, move)
                            self.assertNotEqual(path["move_type"], "unknown")
                            self.assertEqual(path["path"][0], list(move[0]))
                            self.assertEqual(path["path"][-1], list(move[1]))
                    legal = state.get_valid_moves()
                    if not legal or state.is_terminal():
                        break
                    state = state.apply_move(rng.choice(legal))
                    game["state"] = state
        self.assertGreater(checked, 1000)


if __name__ == "__main__":
    unittest.main()
