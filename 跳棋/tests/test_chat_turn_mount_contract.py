from __future__ import annotations

from pathlib import Path
import unittest


class ChatTurnMountContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.source = (root / "static/js/chat.js").read_text(encoding="utf-8")

    def test_live_assistant_turn_is_mounted_before_timers_and_events(self):
        start = self.source.index("function renderTyping()")
        end = self.source.index("function overlayForText")
        body = self.source[start:end]

        create_index = body.index(
            "const item = document.createElement('div')"
        )
        mount_index = body.index("messages.appendChild(item)")
        timer_index = body.index("const taskTimer = window.setInterval")
        handler_index = body.index("function handle(event)")

        self.assertLess(create_index, mount_index)
        self.assertLess(mount_index, timer_index)
        self.assertLess(mount_index, handler_index)

    def test_mount_occurs_exactly_once_inside_render_typing(self):
        start = self.source.index("function renderTyping()")
        end = self.source.index("function overlayForText")
        body = self.source[start:end]
        self.assertEqual(body.count("messages.appendChild(item)"), 1)

    def test_detached_dom_regression_comment_is_present(self):
        self.assertIn("update a detached DOM subtree", self.source)


if __name__ == "__main__":
    unittest.main()
