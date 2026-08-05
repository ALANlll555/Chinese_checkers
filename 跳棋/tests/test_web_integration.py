from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import app as webapp
except ModuleNotFoundError as exc:
    if exc.name == "flask":
        webapp = None
    else:
        raise

from database import GameDatabase
from deepseek_chat import DeepSeekChatService


@unittest.skipIf(webapp is None, "Flask dependency not installed in test environment")
class WebIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        self.db = GameDatabase(Path(self.temp.name) / "web.sqlite3", root / "schema.sql")
        self.old_db = webapp.DB
        self.old_chat = webapp.CHAT
        webapp.DB = self.db
        webapp.CHAT = DeepSeekChatService(self.db)
        webapp.GAMES.clear()
        webapp.app.config.update(TESTING=True)
        self.client = webapp.app.test_client()

    def tearDown(self):
        webapp.GAMES.clear()
        webapp.DB = self.old_db
        webapp.CHAT = self.old_chat
        self.temp.cleanup()

    def test_new_game_move_chat_and_manifest(self):
        response = self.client.post('/api/new_game', json={
            "num_players": 2,
            "mode": "pve",
            "difficulty": 2,
            "human_first": True,
            "api_key": "",
        })
        self.assertEqual(response.status_code, 200)
        game_id = response.get_json()["game_id"]
        game = webapp.GAMES[game_id]
        move = sorted(game["state"].get_valid_moves())[0]

        move_response = self.client.post('/api/move', json={
            "from": list(move[0]), "to": list(move[1]),
        })
        self.assertEqual(move_response.status_code, 200)
        self.assertEqual(len(self.db.get_moves(game_id)), 1)

        chat_response = self.client.post('/api/chat', json={
            "message": "分析局面",
            "thinking": True,
            "show_reasoning": True,
            "context_1m": False,
        })
        self.assertEqual(chat_response.status_code, 200)
        self.assertFalse(chat_response.get_json()["configured"])

        manifest = self.client.get('/api/mcp/manifest').get_json()
        self.assertTrue(manifest["read_only"])
        self.assertIn("evaluate_position", manifest["tools"])


if __name__ == "__main__":
    unittest.main()
