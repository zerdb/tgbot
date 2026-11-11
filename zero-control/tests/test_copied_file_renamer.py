"""Tests for safe batch renaming helpers."""
import tempfile
import unittest
from pathlib import Path

from copied_file_renamer import rename_files, validate_stem, _suggestion_stem


class FileRenameTests(unittest.TestCase):
    def test_validate_stem_rejects_windows_invalid_characters(self):
        with self.assertRaises(ValueError):
            validate_stem("report:final")

    def test_validate_stem_rejects_reserved_names(self):
        with self.assertRaises(ValueError):
            validate_stem("CON")

    def test_suggestion_keeps_extension_out_of_editable_stem(self):
        path = Path("report.pdf")
        self.assertEqual(_suggestion_stem("Отчёт.pdf", path), "Отчёт")

    def test_batch_rename_preserves_extensions(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "scan_001.pdf"
            source.write_text("content", encoding="utf-8")
            count = rename_files([(source, "Скан договора")])
            target = Path(directory) / "Скан договора.pdf"
            self.assertEqual(count, 1)
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "content")

    def test_batch_rename_preserves_compound_archive_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "archive_001.tar.gz"
            source.write_text("content", encoding="utf-8")
            rename_files([(source, "Архив документов")])
            target = Path(directory) / "Архив документов.tar.gz"
            self.assertTrue(target.exists())

    def test_typed_extension_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "scan.pdf"
            source.write_text("content", encoding="utf-8")
            rename_files([(source, "Скан договора.pdf")])
            self.assertTrue((Path(directory) / "Скан договора.pdf").exists())

    def test_batch_rename_supports_swapping_names(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.txt"
            second = Path(directory) / "second.txt"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")
            rename_files([(first, "second"), (second, "first")])
            self.assertEqual(first.read_text(encoding="utf-8"), "two")
            self.assertEqual(second.read_text(encoding="utf-8"), "one")

    def test_batch_rename_rejects_existing_unselected_target(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            target = Path(directory) / "target.txt"
            source.write_text("source", encoding="utf-8")
            target.write_text("target", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                rename_files([(source, "target")])
            self.assertTrue(source.exists())
            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
