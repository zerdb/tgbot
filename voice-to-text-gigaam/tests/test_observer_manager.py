"""Lifecycle tests for the Observer manager without starting real watchers."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from observer.observer_config import save_config
from observer.observer_manager import ObserverManager


class FakeFileCollector:
    instances = []

    def __init__(self, folders, callback):
        self.folders = folders
        self.callback = callback
        self.running = False
        self.__class__.instances.append(self)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


class ObserverManagerTests(unittest.TestCase):
    def setUp(self):
        FakeFileCollector.instances.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.watch = self.root / "watched"
        self.watch.mkdir()
        self.config_path = self.root / "config.json"

    def tearDown(self):
        self.temp.cleanup()

    def make_manager(self, enabled, files_enabled):
        config = {
            "enabled": enabled,
            "categories": {"files": files_enabled},
            "watched_folders": [str(self.watch)],
        }
        save_config(config, self.config_path)
        # ObserverManager reads config.json inside its data directory.
        manager_dir = self.root / "observer_data"
        manager_dir.mkdir(exist_ok=True)
        save_config(config, manager_dir / "config.json")
        return ObserverManager(data_dir=manager_dir)

    def test_disabled_manager_does_not_start_collectors(self):
        manager = self.make_manager(enabled=False, files_enabled=True)
        with patch("observer.observer_manager.FileCollector", FakeFileCollector):
            self.assertFalse(manager.start())
        self.assertFalse(manager.started)
        self.assertEqual(FakeFileCollector.instances, [])

    def test_enabled_file_category_starts_and_stops_collector(self):
        manager = self.make_manager(enabled=True, files_enabled=True)
        with patch("observer.observer_manager.FileCollector", FakeFileCollector):
            self.assertTrue(manager.start())
            self.assertTrue(manager.started)
            self.assertEqual(len(FakeFileCollector.instances), 1)
            collector = FakeFileCollector.instances[0]
            self.assertTrue(collector.running)
            manager.stop()
            self.assertFalse(manager.started)
            self.assertFalse(collector.running)
            self.assertIsNone(manager._file_collector)

    def test_disabled_category_does_not_record_file_event(self):
        manager = self.make_manager(enabled=True, files_enabled=False)
        manager.started = True
        self.assertIsNone(manager.record_event(
            category="files", event_type="created", source="filesystem",
            object_name="private.txt", details={"size_bytes": 1},
        ))
        self.assertEqual(manager.store.count_events(), 0)


if __name__ == "__main__":
    unittest.main()
