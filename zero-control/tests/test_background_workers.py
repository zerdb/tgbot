"""Тесты передачи результатов фоновых задач в очередь GUI."""
import queue
import unittest
from unittest.mock import patch

import background_workers


class BackgroundWorkerTests(unittest.TestCase):
    def test_ai_worker_posts_success_result(self):
        actions = queue.SimpleQueue()
        with patch("background_workers.ask_ai", return_value="Готовый ответ"):
            background_workers.ask_ai_worker("Вопрос", actions)

        self.assertEqual(
            actions.get_nowait(),
            ("ai_chat_result", ("Вопрос", "Готовый ответ", None)),
        )

    def test_ai_worker_posts_error_result(self):
        actions = queue.SimpleQueue()
        with patch("background_workers.ask_ai", side_effect=RuntimeError("Нет связи")):
            background_workers.ask_ai_worker("Вопрос", actions)

        self.assertEqual(
            actions.get_nowait(),
            ("ai_chat_result", ("Вопрос", None, "Нет связи")),
        )


if __name__ == "__main__":
    unittest.main()
