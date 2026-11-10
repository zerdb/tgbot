import unittest

from intent_router import _implicit_file_email_intent


class ImplicitFileEmailIntentTests(unittest.TestCase):
    def test_uses_semantic_person_target_without_email_keyword(self):
        intent = _implicit_file_email_intent(
            "Отправь файлы Богатырю.",
            {"kind": "clarify", "target": {"type": "person", "name": "Богатырю"}, "confidence": 0.8},
        )
        self.assertEqual(intent["action"], "email_compose")
        self.assertEqual(intent["kind"], "execute")
        self.assertEqual(intent["parameters"]["recipient_name"], "Богатырю")
        self.assertTrue(intent["parameters"]["attach_copied_files"])

    def test_extracts_dative_recipient_after_files_without_model(self):
        intent = _implicit_file_email_intent("Отправь файлы Богатырю.")
        self.assertEqual(intent["parameters"]["recipient_name"], "Богатырю")

    def test_extracts_dative_recipient_before_files_without_model(self):
        intent = _implicit_file_email_intent("Перешли Ивану документы.")
        self.assertEqual(intent["parameters"]["recipient_name"], "Ивану")

    def test_does_not_assume_email_for_non_person_destination(self):
        self.assertIsNone(_implicit_file_email_intent("Отправь файлы в архив."))

    def test_asks_for_recipient_when_semantics_identify_person_without_name(self):
        intent = _implicit_file_email_intent(
            "Отправь файлы этому человеку.",
            {"target": {"type": "person", "name": ""}},
        )
        self.assertEqual(intent["kind"], "clarify")
        self.assertEqual(intent["clarification"], "Кому отправить файлы?")


if __name__ == "__main__":
    unittest.main()
