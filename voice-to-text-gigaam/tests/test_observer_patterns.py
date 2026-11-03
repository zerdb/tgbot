"""Tests for local Observer pattern analysis."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from observer.event_store import EventStore
from observer.pattern_analyzer import analyze_patterns


class PatternAnalyzerTests(unittest.TestCase):
    def test_repeated_app_launches_create_explainable_suggestion(self):
        with tempfile.TemporaryDirectory() as temp:
            store = EventStore(Path(temp) / "events.sqlite3")
            for index in range(4):
                store.add_event(
                    "apps", "started", "process", object_name="editor.exe",
                    details={"pid": index + 1},
                    occurred_at=(datetime.now(timezone.utc) - timedelta(minutes=index)).isoformat(timespec="seconds"),
                )
            found = analyze_patterns(store)
            self.assertTrue(any(item["title"] == "Часто запускается: editor.exe" for item in found))

    def test_old_events_are_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            store = EventStore(Path(temp) / "events.sqlite3")
            for index in range(5):
                store.add_event(
                    "apps", "started", "process", object_name="old.exe",
                    occurred_at=(datetime.now(timezone.utc) - timedelta(days=40 + index)).isoformat(timespec="seconds"),
                )
            self.assertEqual(analyze_patterns(store, days=7), [])

    def test_suggestions_are_deduplicated_and_feedback_persists(self):
        with tempfile.TemporaryDirectory() as temp:
            store = EventStore(Path(temp) / "events.sqlite3")
            suggestion = {
                "pattern_key": "unique-pattern",
                "title": "Repeated",
                "description": "Evidence",
            }
            self.assertEqual(store.save_suggestions([suggestion]), 1)
            self.assertEqual(store.save_suggestions([suggestion]), 0)
            item = store.list_suggestions()[0]
            self.assertTrue(store.update_suggestion(item["id"], "dismissed"))
            self.assertEqual(store.list_suggestions()[0]["status"], "dismissed")


if __name__ == "__main__":
    unittest.main()
