import unittest

from contact_resolver import resolve_contact


class ContactResolverTests(unittest.TestCase):
    def setUp(self):
        self.book = {
            "Иван Богатырёв": {"email": "ivan@example.com"},
            "Игорь Богатырев": {"email": "igor@example.com"},
            "Пётр Иванов": {"email": "petr@example.com"},
            "Иван Петров": {"email": "ivan.petrov@example.com"},
            "Анна Смирнова": {"email": "anna@example.com"},
        }

    def test_matches_dative_surname_with_yo_e_normalization(self):
        result = resolve_contact("Богатырю", {"Иван Богатырёв": self.book["Иван Богатырёв"]})
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["contact"]["name"], "Иван Богатырёв")

    def test_matches_dative_first_name(self):
        result = resolve_contact("Петру", {"Пётр Иванов": self.book["Пётр Иванов"]})
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["contact"]["name"], "Пётр Иванов")

    def test_returns_ambiguous_for_duplicate_first_names(self):
        result = resolve_contact("Ивану", self.book)
        self.assertEqual(result["status"], "ambiguous")
        self.assertGreaterEqual(len(result["candidates"]), 2)

    def test_uses_both_name_tokens(self):
        result = resolve_contact("Ивану Петрову", self.book)
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["contact"]["name"], "Иван Петров")

    def test_small_typo_is_tolerated(self):
        result = resolve_contact("Смирново", {"Анна Смирнова": self.book["Анна Смирнова"]})
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["contact"]["name"], "Анна Смирнова")

    def test_phonetic_match_is_offered_for_confirmation(self):
        contact = {"Баграт Бамматов": {"email": "bagrat@example.com"}}
        result = resolve_contact("Богатырю", contact)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidates"][0]["name"], "Баграт Бамматов")

    def test_does_not_match_contact_without_email(self):
        result = resolve_contact("Анне", {"Анна Смирнова": {"email": ""}})
        self.assertEqual(result["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
