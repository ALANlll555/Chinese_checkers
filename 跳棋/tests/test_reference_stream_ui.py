from __future__ import annotations

from pathlib import Path
import unittest


class ReferenceStreamUIContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.app = (root / "app.py").read_text(encoding="utf-8")
        cls.chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
        cls.css = (root / "static/css/style.css").read_text(encoding="utf-8")
        cls.html = (root / "templates/index.html").read_text(encoding="utf-8")

    def test_sse_endpoint_is_observational(self):
        self.assertIn('/api/chat/stream', self.app)
        self.assertIn('text/event-stream', self.app)
        self.assertIn('event_callback=publish', self.app)
        self.assertIn('X-Accel-Buffering', self.app)

    def test_single_turn_orders_rounds_tools_and_answer(self):
        self.assertIn('const roundUnits = new Map()', self.chat)
        self.assertIn('function toolStart(event)', self.chat)
        self.assertIn("title: '最终回答'", self.chat)
        self.assertLess(
            self.chat.index('const roundUnits = new Map()'),
            self.chat.index('function handle(event)'),
        )

    def test_live_events_update_reasoning_and_tools(self):
        self.assertIn("case 'reasoning'", self.chat)
        self.assertIn("case 'tool_start'", self.chat)
        self.assertIn("case 'tool_end'", self.chat)
        self.assertIn('consumeChatStream', self.chat)
        self.assertIn("fetch('/api/chat/stream'", self.chat)

    def test_new_bubble_style_is_loaded(self):
        self.assertIn('.chat-unit.is-collapsed', self.css)
        self.assertIn('.chat-unit-reasoning-text', self.css)
        self.assertIn('.chat-unit-tool-internal', self.css)
        self.assertIn('/static/js/chat.js?v=17', self.html)


if __name__ == "__main__":
    unittest.main()
