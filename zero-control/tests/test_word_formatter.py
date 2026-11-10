"""Regression tests for safe Word formatter suggestion validation."""
import unittest

from word_formatter import validate_format_suggestion


class WordFormatterValidationTests(unittest.TestCase):
    def test_accepts_supported_paragraph_properties(self):
        result = validate_format_suggestion({
            "alignment": "justify",
            "left_indent_pt": 0,
            "first_line_indent_pt": 18,
            "space_after_pt": 6,
            "unsupported_property": "ignored",
        })
        self.assertEqual(result, {
            "alignment": "justify",
            "left_indent_pt": 0.0,
            "first_line_indent_pt": 18.0,
            "space_after_pt": 6.0,
        })

    def test_rejects_unknown_alignment(self):
        with self.assertRaises(ValueError):
            validate_format_suggestion({"alignment": "distributed"})

    def test_rejects_out_of_range_indents(self):
        with self.assertRaises(ValueError):
            validate_format_suggestion({"left_indent_pt": 1000})

    def test_rejects_boolean_numeric_values(self):
        with self.assertRaises(ValueError):
            validate_format_suggestion({"space_after_pt": True})

    def test_rejects_empty_suggestion(self):
        with self.assertRaises(ValueError):
            validate_format_suggestion({"comment": "Looks fine"})

    def test_rejects_non_object_response(self):
        with self.assertRaises(ValueError):
            validate_format_suggestion(["justify"])


if __name__ == "__main__":
    unittest.main()
