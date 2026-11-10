"""Регрессионные тесты локальных намерений и извлечения адресата письма."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# local_intents использует APP_DATA из agent_core; для изолированного теста
# подменяем только этот путь и не загружаем тяжёлые зависимости приложения.
_agent_core = types.ModuleType("agent_core")
_agent_core.APP_DATA = Path(tempfile.gettempdir()) / "zero-control-intent-tests"
sys.modules.setdefault("agent_core", _agent_core)

import local_intents
import intent_router


class LocalIntentValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.rules_path = root / "local_intents.json"
        self.history_path = root / "recognized_intents.json"
        self.rules_patch = patch.object(local_intents, "RULES_PATH", self.rules_path)
        self.history_patch = patch.object(local_intents, "HISTORY_PATH", self.history_path)
        self.rules_patch.start()
        self.history_patch.start()

    def tearDown(self):
        self.rules_patch.stop()
        self.history_patch.stop()
        self.temp_dir.cleanup()

    def test_rejects_parameter_not_supported_by_action(self):
        with self.assertRaisesRegex(ValueError, "не подходят"):
            local_intents.promote_record(
                "record-1", "открой блокнот", "open_application",
                {"app_name": "notepad"},
            )

    def test_rejects_wrong_parameter_type(self):
        with self.assertRaisesRegex(ValueError, "boolean"):
            local_intents.promote_record(
                "record-2", "прикрепи файлы", "email_compose",
                {"attach_copied_files": "true"},
            )

    def test_rejects_missing_required_parameter(self):
        with self.assertRaisesRegex(ValueError, "обязательны"):
            local_intents.promote_record(
                "record-3", "найди файл", "search_files", {},
            )

    def test_accepts_valid_rule_and_matches_it(self):
        local_intents.promote_record(
            "record-4", "открой блокнот", "open_application",
            {"app": "notepad"},
        )
        matched = local_intents.match_local_intent("Открой блокнот!")
        self.assertEqual(matched["action"], "open_application")
        self.assertEqual(matched["parameters"], {"app": "notepad"})


    def test_spoken_wort_alias_routes_directly_to_word(self):
        with patch.object(
            intent_router, "_classify_semantically",
            side_effect=AssertionError("semantic model must not be called"),
        ):
            intent = intent_router._understand_command("Открой Wort.")
        self.assertEqual(intent["action"], "open_application")
        self.assertEqual(intent["parameters"], {"app": "word"})

    def test_word_aliases_route_to_word(self):
        for phrase in ("Открой Word", "Открой Ворд", "Запусти Ворт", "Открой Уорд"):
            with self.subTest(phrase=phrase):
                intent = intent_router._understand_command_rules(phrase)
                self.assertEqual(intent["action"], "open_application")
                self.assertEqual(intent["parameters"], {"app": "word"})

    def test_email_recipient_keeps_first_and_last_name(self):
        intent = intent_router._understand_command_rules(
            "Напиши письмо Ивану Петрову о встрече"
        )
        self.assertEqual(intent["action"], "email_compose")
        self.assertEqual(intent["parameters"]["recipient_name"], "Ивану Петрову")

    def test_email_recipient_after_mail_keyword_keeps_full_name(self):
        intent = intent_router._understand_command_rules(
            "Отправь на почту Ивану Петрову о встрече"
        )
        self.assertEqual(intent["action"], "email_compose")
        self.assertEqual(intent["parameters"]["recipient_name"], "Ивану Петрову")


if __name__ == "__main__":
    unittest.main()
