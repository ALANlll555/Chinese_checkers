from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from board import BoardState
import config
from database import GameDatabase
from deepseek_chat import DeepSeekChatService, resolve_runtime_options


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class ReasoningAndContextControlsTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        self.db = GameDatabase(
            Path(self.temp.name) / "reasoning.sqlite3",
            root / "schema.sql",
        )
        state = BoardState.new_game(2)
        self.game = {
            "game_id": "reasoning-test",
            "state": state,
            "mode": "pve",
            "difficulty": 2,
            "api_key": "test-key",
        }
        self.db.create_game(
            "reasoning-test", state.to_dict(), "pve", 2, 2, True, ""
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_runtime_options_enable_thinking_when_reasoning_is_shown(self):
        options = resolve_runtime_options({
            "thinking": False,
            "show_reasoning": True,
            "context_1m": False,
        })
        self.assertTrue(options["thinking"])
        self.assertTrue(options["show_reasoning"])
        self.assertFalse(options["context_1m"])

    def test_context_switch_changes_budget(self):
        service = DeepSeekChatService(self.db)
        _, standard = service._build_messages(
            "reasoning-test", "context", context_1m=False
        )
        _, extended = service._build_messages(
            "reasoning-test", "context", context_1m=True
        )
        self.assertEqual(standard["context_profile"], "standard")
        self.assertEqual(extended["context_profile"], "1m")
        self.assertEqual(
            standard["context_window_tokens"],
            config.LLM_STANDARD_CONTEXT_WINDOW_TOKENS,
        )
        self.assertEqual(
            extended["context_window_tokens"],
            config.LLM_CONTEXT_WINDOW_TOKENS,
        )
        self.assertGreater(
            extended["input_budget_tokens"],
            standard["input_budget_tokens"],
        )

    def test_thinking_payload_omits_incompatible_sampling_controls(self):
        captured = {}

        def post(*args, **kwargs):
            captured.update(kwargs["json"])
            return FakeResponse({
                "choices": [{"message": {
                    "content": "完成",
                    "reasoning_content": "先核对规则证据。",
                }}]
            })

        service = DeepSeekChatService(self.db, http_post=post)
        service._request(
            "key",
            [{"role": "user", "content": "分析"}],
            thinking=True,
        )
        self.assertEqual(captured["thinking"]["type"], "enabled")
        self.assertEqual(captured["reasoning_effort"], config.LLM_REASONING_EFFORT)
        self.assertNotIn("tool_choice", captured)
        self.assertNotIn("temperature", captured)

    def test_reasoning_is_echoed_across_tool_turn_and_persisted(self):
        payloads = []
        responses = iter([
            FakeResponse({
                "choices": [{"message": {
                    "content": "",
                    "reasoning_content": "第一轮先读取真实棋局。",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "get_game_state",
                            "arguments": "{}",
                        },
                    }],
                }}]
            }),
            FakeResponse({
                "choices": [{"message": {
                    "content": "建议先建立向前梯子。",
                    "reasoning_content": "第二轮结合工具结果比较候选。",
                }}]
            }),
        ])

        def post(*args, **kwargs):
            payloads.append(kwargs["json"])
            return next(responses)

        service = DeepSeekChatService(self.db, http_post=post)
        result = service.reply(
            self.game,
            "分析当前局面",
            options={
                "thinking": True,
                "show_reasoning": True,
                "context_1m": False,
            },
        )

        self.assertEqual(len(payloads), 2)
        assistant_messages = [
            item
            for item in payloads[1]["messages"]
            if item.get("role") == "assistant" and item.get("tool_calls")
        ]
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(
            assistant_messages[0]["reasoning_content"],
            "第一轮先读取真实棋局。",
        )
        self.assertIn("第一轮先读取真实棋局", result["reasoning_content"])
        self.assertIn("第二轮结合工具结果", result["reasoning_content"])
        self.assertTrue(result["thinking_enabled"])
        self.assertFalse(result["context_1m"])

        history = self.db.get_chat_history("reasoning-test")
        metadata = history[-1]["metadata"]
        self.assertEqual(metadata["reasoning_content"], result["reasoning_content"])
        self.assertTrue(metadata["thinking_enabled"])

    def test_reasoning_can_be_hidden(self):
        response = FakeResponse({
            "choices": [{"message": {
                "content": "回答",
                "reasoning_content": "不应返回给界面。",
            }}]
        })
        service = DeepSeekChatService(
            self.db, http_post=lambda *args, **kwargs: response
        )
        result = service.reply(
            self.game,
            "分析",
            options={
                "thinking": True,
                "show_reasoning": False,
                "context_1m": True,
            },
        )
        self.assertEqual(result["reasoning_content"], "")


if __name__ == "__main__":
    unittest.main()
