from __future__ import annotations
import random
import unittest
from pathlib import Path
from board import BoardState
from game_tools import explain_position, validate_candidate_move

class MidgameOverlayLifecycleTestCase(unittest.TestCase):
    def test_random_midgames_never_recommend_empty_source(self):
        for seed in range(80):
            rng=random.Random(seed)
            state=BoardState.new_game(2)
            for _ in range(25):
                legal=state.get_valid_moves()
                if not legal: break
                state=state.apply_move(rng.choice(legal))
            game={'game_id':'g','state':state,'mode':'pve','difficulty':2}
            report=explain_position(game,limit=5)
            pieces=set(state.get_player_pieces(0))
            occupied={p for pid in state.active_players for p in state.get_player_pieces(pid)}
            for candidate in report['candidates']:
                move=candidate['move']
                source=tuple(move['from']); target=tuple(move['to'])
                self.assertIn(source,pieces)
                self.assertNotIn(target,occupied)
                validation=validate_candidate_move(game,source,target,0)
                self.assertTrue(validation['valid'])
    def test_frontend_has_draw_time_guard_and_replay_invalidation(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'static/js/game.js').read_text(encoding='utf-8')
        self.assertIn('validateCurrentAIAnalysisOverlay',source)
        self.assertIn('rawPayload',source)
        for name in ('startReplay','replayStepTo','exitReplay'):
            start=source.index('function '+name)
            body=source[start:start+3500]
            self.assertIn('AIChat.onGameStateChanged',body)
    def test_multijump_is_presented_as_one_piece(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'static/js/game.js').read_text(encoding='utf-8')
        self.assertIn('translucent copy of the SAME source piece',source)
        self.assertIn('同一颗棋依次落点',source)
if __name__=='__main__': unittest.main()
