from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from board import BoardState
from database import GameDatabase
from deepseek_chat import DeepSeekChatService


def sse(payload):
    return "data: " + json.dumps(payload, ensure_ascii=False)


class FakeStreamResponse:
    def __init__(self, lines):
        self.lines = lines
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_lines(self, chunk_size=1, decode_unicode=True):
        self.chunk_size = chunk_size
        self.decode_unicode = decode_unicode
        yield from self.lines

    def close(self):
        self.closed = True


class TrueUpstreamStreamingTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        self.db = GameDatabase(
            Path(self.temp.name) / "stream.sqlite3",
            root / "schema.sql",
        )
        state = BoardState.new_game(2)
        self.game = {
            "game_id": "true-stream",
            "state": state,
            "mode": "pve",
            "difficulty": 3,
            "api_key": "test-key",
            "deepseek_settings": {
                "thinking": True,
                "show_reasoning": True,
                "context_1m": True,
                "model": "deepseek-v4-flash",
                "reasoning_effort": "high",
            },
        }
        self.db.create_game(
            "true-stream", state.to_dict(), "pve", 3, 2, True, ""
        )

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def responses():
        first = FakeStreamResponse([
            sse({"choices": [{"delta": {
                "role": "assistant",
                "reasoning_content": "先",
            }, "finish_reason": None}]}),
            sse({"choices": [{"delta": {
                "reasoning_content": "读取棋局。",
            }, "finish_reason": None}]}),
            sse({"choices": [{"delta": {
                "content": "我先读取事实。",
            }, "finish_reason": None}]}),
            sse({"choices": [{"delta": {
                "tool_calls": [{
                    "index": 0,
                    "id": "call-state",
                    "type": "function",
                    "function": {
                        "name": "get_game_",
                        "arguments": "",
                    },
                }],
            }, "finish_reason": None}]}),
            sse({"choices": [{"delta": {
                "tool_calls": [{
                    "index": 0,
                    "function": {
                        "name": "state",
                        "arguments": "{}",
                    },
                }],
            }, "finish_reason": "tool_calls"}]}),
            sse({
                "choices": [],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            }),
            "data: [DONE]",
        ])
        second = FakeStreamResponse([
            sse({"choices": [{"delta": {
                "role": "assistant",
                "reasoning_content": "结合",
            }, "finish_reason": None}]}),
            sse({"choices": [{"delta": {
                "reasoning_content": "工具结果。",
            }, "finish_reason": None}]}),
            sse({"choices": [{"delta": {
                "content": "最终",
            }, "finish_reason": None}]}),
            sse({"choices": [{"delta": {
                "content": "回答。",
            }, "finish_reason": "stop"}]}),
            "data: [DONE]",
        ])
        return iter([first, second])

    def test_true_stream_assembles_tool_calls_and_emits_deltas(self):
        responses = self.responses()
        payloads = []

        def post(*args, **kwargs):
            payloads.append(kwargs["json"])
            self.assertTrue(kwargs.get("stream"))
            return next(responses)

        events = []
        service = DeepSeekChatService(self.db, http_post=post)
        result = service.reply(
            self.game,
            "分析当前局面",
            event_callback=events.append,
        )

        self.assertEqual(len(payloads), 2)
        for payload in payloads:
            self.assertTrue(payload["stream"])
            self.assertEqual(
                payload["stream_options"],
                {"include_usage": True},
            )

        second_messages = payloads[1]["messages"]
        assistant_tool = next(
            item for item in second_messages
            if item.get("role") == "assistant"
            and item.get("tool_calls")
        )
        self.assertEqual(
            assistant_tool["reasoning_content"],
            "先读取棋局。",
        )
        self.assertEqual(
            assistant_tool["content"],
            "我先读取事实。",
        )
        self.assertEqual(
            assistant_tool["tool_calls"][0]["function"]["name"],
            "get_game_state",
        )
        self.assertEqual(
            assistant_tool["tool_calls"][0]["function"]["arguments"],
            "{}",
        )
        self.assertTrue(
            any(
                item.get("role") == "tool"
                for item in second_messages
            )
        )

        event_types = [event["type"] for event in events]
        self.assertGreaterEqual(event_types.count("reasoning"), 4)
        self.assertIn("content_delta", event_types)
        self.assertIn("tool_delta", event_types)
        self.assertIn("upstream_done", event_types)
        self.assertIn("tool_start", event_types)
        self.assertIn("tool_end", event_types)

        self.assertEqual(result["answer"], "最终回答。")
        self.assertEqual(
            result["reasoning_content"],
            "先读取棋局。\n\n---\n\n结合工具结果。",
        )
        self.assertTrue(
            result["context_usage"]["upstream_stream_enabled"]
        )
        self.assertEqual(
            len(result["context_usage"]["upstream_rounds"]),
            2,
        )

    def test_tool_reasoning_transcript_survives_next_user_turn(self):
        responses = self.responses()
        service = DeepSeekChatService(
            self.db,
            http_post=lambda *args, **kwargs: next(responses),
        )
        service.reply(
            self.game,
            "第一轮",
            event_callback=lambda event: None,
        )

        history = self.db.get_chat_history("true-stream")
        metadata = history[-1]["metadata"]
        transcript = metadata["agent_messages"]
        self.assertTrue(
            any(
                item.get("role") == "assistant"
                and item.get("tool_calls")
                and item.get("reasoning_content")
                == "先读取棋局。"
                for item in transcript
            )
        )
        self.assertTrue(
            any(
                item.get("role") == "tool"
                for item in transcript
            )
        )

        messages, usage = service._build_messages(
            "true-stream",
            "current context",
            context_1m=True,
        )
        self.assertTrue(
            usage["tool_reasoning_history_enabled"]
        )
        self.assertTrue(
            any(
                item.get("role") == "assistant"
                and item.get("tool_calls")
                and item.get("reasoning_content")
                == "先读取棋局。"
                for item in messages
            )
        )
        self.assertTrue(
            any(
                item.get("role") == "tool"
                for item in messages
            )
        )


if __name__ == "__main__":
    unittest.main()
