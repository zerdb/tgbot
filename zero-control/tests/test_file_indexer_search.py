"""Regression tests for Latin/Cyrillic filename search aliases."""
import sys
import tempfile
import types
import unittest
from pathlib import Path

_agent_core = types.ModuleType("agent_core")
_agent_core.APP_DATA = Path(tempfile.gettempdir()) / "zero-control-file-index-tests"
sys.modules.setdefault("agent_core", _agent_core)

from file_indexer import _search_needle_variants


class SearchNeedleVariantTests(unittest.TestCase):
    def test_latin_asr_initialism_matches_cyrillic_filename(self):
        self.assertEqual(_search_needle_variants("LPU"), ["lpu", "лпу"])

    def test_cyrillic_initialism_matches_latin_filename(self):
        self.assertEqual(_search_needle_variants("ЛПУ"), ["лпу", "lpu"])

    def test_case_and_punctuation_are_normalized(self):
        self.assertEqual(_search_needle_variants(" L-P-U! "), ["lpu", "лпу"])

    def test_empty_query_has_no_variants(self):
        self.assertEqual(_search_needle_variants(" ... "), [])

    def test_mixed_scripts_keep_original_without_guessing(self):
        self.assertEqual(_search_needle_variants("LPUадреса"), ["lpuадреса"])


if __name__ == "__main__":
    unittest.main()
