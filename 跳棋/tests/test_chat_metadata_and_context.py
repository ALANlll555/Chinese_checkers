from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from board import BoardState
import config
from database import GameDatabase
from deepseek_chat import DeepSeekChatService

class FakeResponse:
    def __init__(self, payload): self.payload=payload
    def raise_for_status(self): return None
    def json(self): return self.payload

class MetadataAndContextTestCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(__file__).resolve().parents[1]
        self.db=GameDatabase(Path(self.temp.name)/'db.sqlite3', root/'schema.sql')
        state=BoardState.new_game(2)
        self.game={'game_id':'meta','state':state,'mode':'pve','difficulty':2,'api_key':''}
        self.db.create_game('meta',state.to_dict(),'pve',2,2,True,'')
    def tearDown(self): self.temp.cleanup()
    def test_structured_explanation_round_trips_through_sql(self):
        result=DeepSeekChatService(self.db).reply(self.game,'给我一个推进方案')
        row=self.db.get_chat_history('meta')[-1]
        self.assertEqual(row['role'],'assistant')
        self.assertTrue(row['metadata']['coach_report']['candidates'])
        self.assertTrue(row['metadata']['board_overlay']['moves'])
    def test_one_million_context_defaults_and_budget(self):
        self.assertEqual(config.LLM_CONTEXT_WINDOW_TOKENS,1_000_000)
        self.assertLess(config.LLM_INPUT_BUDGET_TOKENS,config.LLM_CONTEXT_WINDOW_TOKENS)
        service=DeepSeekChatService(self.db)
        messages,usage=service._build_messages('meta','context')
        self.assertLessEqual(usage['estimated_input_tokens'],usage['input_budget_tokens'])
        self.assertTrue(usage['cache_prefix_stable'])
    def test_short_model_answer_gets_local_explanation(self):
        self.game['api_key']='key'
        service=DeepSeekChatService(self.db,http_post=lambda *a,**k:FakeResponse({'choices':[{'message':{'content':'走这里。'}}]}))
        result=service.reply(self.game,'推荐方案')
        self.assertEqual(result['answer'],'走这里。')
        self.assertTrue(result['coach_report']['candidates'])
        self.assertTrue(result['board_overlay']['moves'])
        self.assertTrue(result['context_usage']['context_window_tokens'])
if __name__=='__main__': unittest.main()
