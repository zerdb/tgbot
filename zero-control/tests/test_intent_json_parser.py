import unittest

from intent_router import _parse_intent_json


class IntentJsonParserTests(unittest.TestCase):
    def test_parses_plain_json_with_nested_objects(self):
        parsed = _parse_intent_json(
            '{"kind":"execute","parameters":{"recipient_name":"Иван"}}'
        )
        self.assertEqual(parsed["parameters"]["recipient_name"], "Иван")

    def test_parses_json_inside_markdown_fence(self):
        parsed = _parse_intent_json(
            'Результат:\n```json\n{"kind":"respond","action":"ai_chat"}\n```'
        )
        self.assertEqual(parsed["action"], "ai_chat")

    def test_ignores_braces_inside_json_strings(self):
        parsed = _parse_intent_json(
            '{"kind":"respond","response":"текст с фигурными скобками {пример}"}'
        )
        self.assertEqual(parsed["response"], "текст с фигурными скобками {пример}")

    def test_rejects_response_without_json_object(self):
        with self.assertRaisesRegex(RuntimeError, "корректный JSON-объект"):
            _parse_intent_json("не получилось сформировать ответ")


if __name__ == "__main__":
    unittest.main()
