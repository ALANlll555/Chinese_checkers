from __future__ import annotations

from pathlib import Path
import unittest


class ChatScrollFollowContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
        cls.css = (root / "static/css/style.css").read_text(encoding="utf-8")

    def test_scroll_is_conditional_not_unconditional(self):
        self.assertIn("let chatAutoFollow = true", self.chat)
        self.assertIn("function isChatNearBottom", self.chat)
        self.assertIn("function scrollChatMessages", self.chat)
        self.assertIn("if (!chatAutoFollow)", self.chat)

        start = self.chat.index("function renderTyping()")
        end = self.chat.index("function overlayForText")
        body = self.chat[start:end]
        self.assertNotIn(
            "messages.scrollTop = messages.scrollHeight",
            body,
        )
        self.assertIn("scrollChatMessages(messages)", body)

    def test_user_scroll_disables_auto_follow(self):
        self.assertIn("messages.addEventListener('scroll'", self.chat)
        self.assertIn("event.deltaY < 0", self.chat)
        self.assertIn("chatAutoFollow = false", self.chat)

    def test_return_to_bottom_control_exists(self):
        self.assertIn("chat-scroll-bottom", self.chat)
        self.assertIn("↓ 回到底部", self.chat)
        self.assertIn(".chat-scroll-bottom", self.css)

    def test_touch_and_overscroll_are_supported(self):
        self.assertIn("touchmove", self.chat)
        self.assertIn("overscroll-behavior: contain", self.css)
        self.assertIn("touch-action: pan-y", self.css)


if __name__ == "__main__":
    unittest.main()
