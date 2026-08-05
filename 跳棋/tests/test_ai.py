"""AI 升级回归测试。使用 Python 标准库 unittest，无新增依赖。"""

import os
import random
import sys
import time
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from ai import (  # noqa: E402
    ai_greedy,
    ai_minimax,
    ai_random,
    clear_evaluation_cache,
    evaluate,
    evaluate_components,
    get_local_candidates,
)
from board import BoardState, GOAL_SETS, HOME_SETS  # noqa: E402
import config as cfg  # noqa: E402


class AITestCase(unittest.TestCase):
    def setUp(self):
        clear_evaluation_cache()

    def test_components_are_the_five_rule_driven_features(self):
        state = BoardState.new_game(2)
        result = evaluate_components(state, state.current_player)
        self.assertEqual(
            set(result),
            {
                "goal_assignment_distance",
                "last_piece_distance",
                "forward_jump_value",
                "ladder_potential",
                "home_delay",
                "score",
            },
        )
        self.assertEqual(result["score"], evaluate(state, state.current_player))

    def test_all_three_algorithms_return_legal_moves(self):
        state = BoardState.new_game(2)
        legal = set(state.get_valid_moves())
        self.assertIn(ai_random(state, random.Random(1)), legal)
        self.assertIn(ai_greedy(state, random.Random(2)), legal)
        self.assertIn(
            ai_minimax(state, depth=2, time_limit=0.5, rng=random.Random(3)),
            legal,
        )

    def test_easy_randomness_never_leaves_local_shortlist(self):
        state = BoardState.new_game(2)
        allowed = set(get_local_candidates(state, 1))
        self.assertTrue(allowed)
        observed = {
            ai_random(state, random.Random(seed))
            for seed in range(40)
        }
        self.assertTrue(observed.issubset(allowed))
        if len(allowed) > 1:
            self.assertGreater(len(observed), 1)

    def test_medium_randomness_never_leaves_local_shortlist(self):
        state = BoardState.new_game(2)
        allowed = set(get_local_candidates(state, 2))
        observed = {
            ai_greedy(state, random.Random(seed))
            for seed in range(20)
        }
        self.assertTrue(observed.issubset(allowed))

    def test_forward_move_does_not_worsen_best_one_step_evaluation(self):
        state = BoardState.new_game(2)
        pid = state.current_player
        before = evaluate(state, pid)
        best_after = max(evaluate(state.apply_move(move), pid) for move in state.get_valid_moves())
        self.assertGreater(best_after, before)

    def test_completed_goal_is_decisively_rewarded(self):
        state = BoardState.new_game(2)
        pid = 0
        # 构造规则允许的已完成局面，只用于验证终局评价。
        for pos in list(state._pieces[pid]):
            state.board[pos[0]][pos[1]] = 0
        state._pieces[pid] = set(GOAL_SETS[pid])
        for pos in GOAL_SETS[pid]:
            state.board[pos[0]][pos[1]] = pid + 1
        state._update_score(pid)
        self.assertEqual(state.get_winner(), pid)
        self.assertGreater(evaluate(state, pid), cfg.AI_WIN_SCORE / 2)

    def test_home_delay_increases_with_stagnation(self):
        state = BoardState.new_game(2)
        pid = state.current_player
        initial = evaluate_components(state, pid)["home_delay"]
        # 添加己方历史回合但不改变棋盘，专门验证阶段性滞留惩罚。
        src = next(iter(HOME_SETS[pid]))
        for _ in range(cfg.PIECES_PER_PLAYER):
            state.move_history.append((src[0], src[1], src[0], src[1], pid))
        clear_evaluation_cache()
        later = evaluate_components(state, pid)["home_delay"]
        self.assertGreater(later, initial)

    def test_hard_multiplayer_moves_are_legal(self):
        for players in (3, 4, 6):
            state = BoardState.new_game(players)
            move = ai_minimax(
                state, depth=2, time_limit=0.25,
                rng=random.Random(players),
            )
            self.assertIn(move, state.get_valid_moves())

    def test_hard_ai_respects_time_budget_with_small_tolerance(self):
        state = BoardState.new_game(2)
        started = time.perf_counter()
        move = ai_minimax(state, depth=4, time_limit=0.15, rng=random.Random(4))
        elapsed = time.perf_counter() - started
        self.assertIn(move, state.get_valid_moves())
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
