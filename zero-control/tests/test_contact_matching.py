"""Regression tests for inflected and ASR-misheard Russian contact names."""
import unittest
from contact_matching import best_contact_matches

class ContactMatchingTests(unittest.TestCase):
    def test_dative_name_with_single_vowel_asr_difference(self):
        self.assertEqual(best_contact_matches("Богатырю", ["Багатыр Бамматов"]), ["Багатыр Бамматов"])

    def test_exact_inflected_full_name(self):
        self.assertEqual(best_contact_matches("Ивану Петрову", ["Иван Петров"]), ["Иван Петров"])

    def test_ambiguous_first_name_does_not_choose_arbitrarily(self):
        self.assertEqual(best_contact_matches("Богатырю", ["Багатыр Бамматов", "Багатыр Бамматова"]), ["Багатыр Бамматов", "Богатыр Иванов"])

    def test_unrelated_contact_is_not_matched(self):
        self.assertEqual(best_contact_matches("Богатырю", ["Александр Смирнов"]), [])

if __name__ == "__main__":
    unittest.main()