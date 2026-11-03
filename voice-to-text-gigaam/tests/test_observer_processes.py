"""Tests for process metadata collection without inspecting real user processes."""
import unittest

from observer.process_collector import ProcessCollector


class ProcessCollectorTests(unittest.TestCase):
    def test_detects_started_and_stopped_processes(self):
        snapshots = [
            {10: {"name": "editor.exe", "path": "C:/Apps/editor.exe"}},
            {
                10: {"name": "editor.exe", "path": "C:/Apps/editor.exe"},
                11: {"name": "music.exe", "path": "C:/Apps/music.exe"},
            },
            {11: {"name": "music.exe", "path": "C:/Apps/music.exe"}},
        ]
        events = []
        collector = ProcessCollector(
            lambda **event: events.append(event),
            process_provider=lambda: snapshots.pop(0),
        )
        self.assertEqual(collector.scan_once(initial=True), 0)
        self.assertEqual(collector.scan_once(), 1)
        self.assertEqual(events[-1]["event_type"], "started")
        self.assertEqual(events[-1]["object_name"], "music.exe")
        self.assertEqual(collector.scan_once(), 1)
        self.assertEqual(events[-1]["event_type"], "stopped")
        self.assertEqual(events[-1]["details"], {"pid": 10})

    def test_excluded_process_is_not_reported(self):
        events = []
        collector = ProcessCollector(
            lambda **event: events.append(event),
            excluded_processes=["private.exe"],
            process_provider=lambda: {
                20: {"name": "private.exe", "path": "C:/Apps/private.exe"}
            },
        )
        collector.scan_once(initial=True)
        self.assertEqual(collector.scan_once(), 0)
        self.assertEqual(events, [])

    def test_does_not_collect_command_line_or_window_content(self):
        events = []
        collector = ProcessCollector(
            lambda **event: events.append(event),
            process_provider=lambda: {
                30: {"name": "editor.exe", "path": "C:/Apps/editor.exe"}
            },
        )
        collector.scan_once(initial=True)
        collector.process_provider = lambda: {
            30: {"name": "editor.exe", "path": "C:/Apps/editor.exe"},
            31: {"name": "browser.exe", "path": "C:/Apps/browser.exe"},
        }
        collector.scan_once()
        self.assertNotIn("command_line", events[0]["details"])
        self.assertNotIn("window_title", events[0]["details"])


if __name__ == "__main__":
    unittest.main()
