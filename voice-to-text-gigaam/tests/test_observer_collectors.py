"""Tests for focus and protected clipboard collectors."""
import unittest

from observer.clipboard_collector import ClipboardCollector, redact_sensitive
from observer.focus_collector import FocusCollector


class CollectorTests(unittest.TestCase):
    def test_clipboard_redacts_secret_patterns(self):
        self.assertIsNone(redact_sensitive("password: hunter2"))
        self.assertIsNone(redact_sensitive("sk-12345678901234567890"))
        self.assertEqual(redact_sensitive("обычный текст для заметки"), "обычный текст для заметки")

    def test_clipboard_records_only_changed_text(self):
        sequence = [1]
        events = []
        collector = ClipboardCollector(
            lambda **event: events.append(event),
            reader=lambda: "hello world",
            sequence_provider=lambda: sequence[0],
        )
        self.assertTrue(collector.scan_once())
        self.assertFalse(collector.scan_once())
        sequence[0] = 2
        self.assertFalse(collector.scan_once())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["details"]["text"], "hello world")

    def test_focus_duration_is_recorded_on_switch(self):
        now = [100.0]
        current = [{"hwnd": 10, "pid": 20, "name": "editor.exe", "path": "C:/editor.exe", "title": "Notes"}]
        events = []
        collector = FocusCollector(lambda **event: events.append(event), provider=lambda: current[0])
        collector._current = current[0]
        collector._since = now[0]
        now[0] += 12.5
        current[0] = {"hwnd": 11, "pid": 21, "name": "browser.exe", "path": "C:/browser.exe", "title": "Docs"}
        collector._flush(now[0])
        self.assertEqual(events[0]["details"]["duration_seconds"], 12.5)
        self.assertEqual(events[0]["object_name"], "editor.exe")


if __name__ == "__main__":
    unittest.main()
