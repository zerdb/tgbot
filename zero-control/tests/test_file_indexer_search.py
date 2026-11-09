"""Regression tests for Latin/Cyrillic filename search aliases."""
import sys
import tempfile
import types
import unittest
from pathlib import Path

_agent_core = types.ModuleType("agent_core")
_agent_core.APP_DATA = Path(tempfile.gettempdir()) / "zero-control-file-index-tests"
sys.modules.setdefault("agent_core", _agent_core)

from file_indexer import _search_file_rows, _search_needle_variants


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

    def test_sqlite_fallback_uses_persisted_normalized_text(self):
        import sqlite3

        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE files (full_path TEXT, search_text TEXT)"
        )
        connection.execute(
            "INSERT INTO files VALUES (?, ?)",
            (r"C:\Docs\ЛПУ адреса.pdf", "лпуадреса cдocsлпуадресаpdf"),
        )
        rows, mode = _search_file_rows(connection, "лпу")
        self.assertEqual(rows, [(r"C:\Docs\ЛПУ адреса.pdf",)])
        self.assertIn("SQLite fallback", mode)
        connection.close()

    def test_fts5_returns_empty_without_scanning_fallback(self):
        import sqlite3

        connection = sqlite3.connect(":memory:")
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE files_fts USING fts5(full_path UNINDEXED, search_text, tokenize='trigram')"
            )
        except sqlite3.OperationalError:
            self.skipTest("SQLite build does not include FTS5 trigram tokenizer")
        connection.execute(
            "CREATE TABLE files (full_path TEXT, search_text TEXT)"
        )
        connection.execute(
            "INSERT INTO files VALUES (?, ?)", (r"C:\Docs\other.pdf", "otherpdf")
        )
        rows, mode = _search_file_rows(connection, "missing")
        self.assertEqual(rows, [])
        self.assertEqual(mode, "FTS5 trigram")
        connection.close()


if __name__ == "__main__":
    unittest.main()
