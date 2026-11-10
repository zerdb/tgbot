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



    def test_prompt_evaluates_absolute_quality_not_only_consistency(self):
        from word_formatter import _build_analysis_messages

        profiles = [
            {"paragraph": n, "style": "Обычный", "alignment": 0,
             "left_indent_pt": 0.0, "right_indent_pt": 0.0,
             "first_line_indent_pt": 0.0, "space_before_pt": 0.0,
             "space_after_pt": 0.0}
            for n in range(1, 4)
        ]
        messages = _build_analysis_messages("Первый абзац.\\nВторой абзац.\\nТретий абзац.", profiles)
        self.assertIn("одинаково оформлены", messages[0]["content"])
        self.assertIn("space_after_pt=6", messages[0]["content"])
        self.assertIn("не являются причиной отвечать no_changes", messages[1]["content"])

    def test_prompt_protects_text_and_character_formatting(self):
        from word_formatter import _build_analysis_messages

        messages = _build_analysis_messages("Тест", [])
        self.assertIn("жирность, курсив, подчёркивание", messages[0]["content"])
        self.assertIn("только свойства абзацев", messages[0]["content"])

    def test_parses_valid_suggestion(self):
        from word_formatter import parse_format_response

        suggestion, reason = parse_format_response('{"alignment":"justify","space_after_pt":6}')
        self.assertEqual(suggestion, {"alignment": "justify", "space_after_pt": 6.0})
        self.assertIsNone(reason)

    def test_parses_explicit_no_changes(self):
        from word_formatter import parse_format_response

        suggestion, reason = parse_format_response(
            '{"no_changes":true,"reason":"Абзацы оформлены единообразно."}'
        )
        self.assertIsNone(suggestion)
        self.assertEqual(reason, "Абзацы оформлены единообразно.")

    def test_parses_fenced_json(self):
        from word_formatter import parse_format_response

        answer = "```json\n{\"alignment\":\"left\"}\n```"
        suggestion, reason = parse_format_response(answer)
        self.assertEqual(suggestion, {"alignment": "left"})
        self.assertIsNone(reason)

    def test_rejects_empty_or_malformed_response(self):
        from word_formatter import parse_format_response

        for answer in ("", "{}", "not json", "[]"):
            with self.subTest(answer=answer):
                with self.assertRaises(ValueError):
                    parse_format_response(answer)

    def test_rejects_non_object_response(self):
        with self.assertRaises(ValueError):
            validate_format_suggestion(["justify"])


if __name__ == "__main__":
    unittest.main()
