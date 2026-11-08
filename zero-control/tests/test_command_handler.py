"""Тесты диспетчеризации намерений без запуска GUI."""
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from command_handler import CommandHandler


class CommandHandlerTests(unittest.TestCase):
    def setUp(self):
        self.actions = queue.SimpleQueue()
        self.ui = SimpleNamespace(root=object())
        self.handler = CommandHandler(
            get_ui=lambda: self.ui,
            get_ui_thread_id=lambda: None,
            ui_actions=self.actions,
        )

    def test_respond_intent_is_forwarded_to_ai_queue(self):
        intent = {
            "kind": "respond",
            "action": "respond",
            "parameters": {"question": "Сколько будет два плюс два?"},
        }
        with patch("intent_router.understand_command", return_value=intent):
            self.handler.handle_command("Ответь на вопрос")

        self.assertEqual(self.actions.get_nowait(), ("busy", "Обработка…"))
        self.assertEqual(self.actions.get_nowait(), ("busy", "Жду ответ ИИ…"))
        self.assertEqual(
            self.actions.get_nowait(),
            ("ai_chat", "Сколько будет два плюс два?"),
        )

    def test_low_confidence_intent_is_not_executed(self):
        intent = {
            "kind": "execute",
            "action": "lock_computer",
            "confidence": 0.2,
            "parameters": {},
        }
        with patch("intent_router.understand_command", return_value=intent):
            with patch("command_handler.lock_computer") as lock_computer:
                self.handler.handle_command("сделай что-нибудь")

        lock_computer.assert_not_called()
        self.assertEqual(self.actions.get_nowait(), ("busy", "Обработка…"))
        self.assertEqual(self.actions.get_nowait(), ("busy", None))


if __name__ == "__main__":
    unittest.main()
