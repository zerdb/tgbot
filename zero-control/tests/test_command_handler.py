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

    def test_read_clipboard_text_command_is_recognized_without_intent_router(self):
        self.assertTrue(self.handler._is_read_clipboard_text_command("Прочитай текст из буфера"))
        self.assertTrue(self.handler._is_read_clipboard_text_command("Зачитай буфер обмена"))
        self.assertFalse(self.handler._is_read_clipboard_text_command("Прочитай выделенный текст"))

    def test_read_clipboard_text_uses_piper_and_does_not_modify_clipboard(self):
        with patch("pyperclip.paste", return_value="Текст для чтения") as paste:
            with patch("notifications.speak_clipboard_text") as speak:
                self.handler._read_clipboard_text()

        paste.assert_called_once_with()
        speak.assert_called_once_with("Текст для чтения")

    def test_clipboard_speech_voice_controls_only_run_during_reading(self):
        with patch("notifications.is_clipboard_reading_active", return_value=True):
            with patch("notifications.pause_clipboard_reading") as pause:
                self.assertTrue(self.handler._handle_clipboard_speech_control("Пауза"))
                pause.assert_called_once_with()

        with patch("notifications.is_clipboard_reading_active", return_value=False):
            self.assertFalse(self.handler._handle_clipboard_speech_control("Стоп"))

    def test_clipboard_speech_speed_commands(self):
        with patch("notifications.is_clipboard_reading_active", return_value=True):
            with patch("notifications.increase_clipboard_reading_speed") as faster:
                self.assertTrue(self.handler._handle_clipboard_speech_control("Быстрее"))
                faster.assert_called_once_with()
            with patch("notifications.decrease_clipboard_reading_speed") as slower:
                self.assertTrue(self.handler._handle_clipboard_speech_control("Медленнее"))
                slower.assert_called_once_with()

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
