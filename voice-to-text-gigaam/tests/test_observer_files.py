"""Tests for the Observer file collector and metadata-only event storage."""
import tempfile
import unittest
from pathlib import Path

from observer.event_store import EventStore
from observer.file_collector import FileCollector


class FileCollectorTests(unittest.TestCase):
    def test_detects_create_modify_and_delete_without_reading_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Documents"
            root.mkdir()
            events = []
            collector = FileCollector([root], lambda **event: events.append(event))
            collector.scan_once(initial=True)
            sample = root / "note.txt"
            sample.write_text("first", encoding="utf-8")
            self.assertEqual(collector.scan_once(), 1)
            self.assertEqual(events[-1]["event_type"], "created")
            sample.write_text("second version", encoding="utf-8")
            self.assertEqual(collector.scan_once(), 1)
            self.assertEqual(events[-1]["event_type"], "modified")
            sample.unlink()
            self.assertEqual(collector.scan_once(), 1)
            self.assertEqual(events[-1]["event_type"], "deleted")
            self.assertNotIn("content", events[-1]["details"])

    def test_event_store_persists_file_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            store = EventStore(Path(temp) / "events.sqlite3")
            event_id = store.add_event(
                category="files", event_type="created", source="filesystem",
                object_name="report.docx", object_path="C:/Users/Test/Documents/report.docx",
                details={"size_bytes": 42}
            )
            self.assertIsInstance(event_id, int)
            events = store.list_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["details"]["size_bytes"], 42)


if __name__ == "__main__":
    unittest.main()
