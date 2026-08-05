from __future__ import annotations

from pathlib import Path
import unittest


class ProcessContinuityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.deepseek = (root / "deepseek_chat.py").read_text(encoding="utf-8")
        cls.app = (root / "app.py").read_text(encoding="utf-8")
        cls.chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
        cls.css = (root / "static/css/style.css").read_text(encoding="utf-8")

    def test_backend_emits_post_tool_synthesis_and_final_validation(self):
        self.assertIn("MCP 结果已汇总，DeepSeek 正在综合工具证据", self.deepseek)
        self.assertIn("模型草稿已返回，正在复核规则证据与棋盘高亮", self.deepseek)
        self.assertIn("规则复核完成，正在组装最终回答与交互候选", self.deepseek)

    def test_tool_start_does_not_finish_the_process_timer(self):
        start = self.chat.index("function toolStart(event)")
        end = self.chat.index("function toolEnd(event)")
        body = self.chat[start:end]
        self.assertNotIn("finishThinking()", body)
        self.assertIn("setPhase(", body)

    def test_phase_timeline_and_heartbeat_are_visible(self):
        self.assertIn("chat-process-phase-list", self.chat)
        self.assertIn("case 'heartbeat'", self.chat)
        self.assertIn("events.get(timeout=1.0)", self.app)
        self.assertIn(".chat-process-phase", self.css)


if __name__ == "__main__":
    unittest.main()
