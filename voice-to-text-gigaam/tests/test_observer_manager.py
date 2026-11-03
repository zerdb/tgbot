"""Lifecycle tests for the approved automatic Observer collectors."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from observer.observer_config import save_config
from observer.observer_manager import ObserverManager


class FakeCollector:
    instances = []

    def __init__(self, *args, **kwargs):
        self.running = False
        self.__class__.instances.append(self)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


class ObserverManagerTests(unittest.TestCase):
    def setUp(self):
        FakeCollector.instances.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.watch = self.root / "watched"
        self.watch.mkdir()
        self.data_dir = self.root / "observer_data"
        self.data_dir.mkdir()
        save_config({
            "enabled": False,
            "categories": {
                "files": False, "apps": False, "focus": False,
                "clipboard": False, "browser": True,
            },
            "watched_folders": [str(self.watch)],
        }, self.data_dir / "config.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_manager_enables_metadata_and_keeps_clipboard_off(self):
        manager = ObserverManager(data_dir=self.data_dir)
        self.assertTrue(manager.is_enabled)
        self.assertTrue(manager.config["categories"]["files"])
        self.assertTrue(manager.config["categories"]["apps"])
        self.assertTrue(manager.config["categories"]["focus"])
        self.assertFalse(manager.config["categories"]["clipboard"])
        self.assertNotIn("browser", manager.config["categories"])

    def test_starts_metadata_collectors_but_not_clipboard(self):
        manager = ObserverManager(data_dir=self.data_dir)
        with patch("observer.observer_manager.FileCollector", FakeCollector), \
             patch("observer.observer_manager.ProcessCollector", FakeCollector), \
             patch("observer.observer_manager.FocusCollector", FakeCollector):
            self.assertTrue(manager.start())
            self.assertTrue(manager.started)
            self.assertEqual(len(FakeCollector.instances), 3)
            self.assertTrue(all(item.running for item in FakeCollector.instances))
            self.assertIsNone(manager._clipboard_collector)
            manager.stop()
            self.assertFalse(manager.started)
            self.assertTrue(all(not item.running for item in FakeCollector.instances))

    def test_clipboard_starts_only_after_explicit_checkbox_setting(self):
        manager = ObserverManager(data_dir=self.data_dir)
        manager.config["categories"]["clipboard"] = True
        with patch("observer.observer_manager.FileCollector", FakeCollector), \
             patch("observer.observer_manager.ProcessCollector", FakeCollector), \
             patch("observer.observer_manager.FocusCollector", FakeCollector), \
             patch("observer.observer_manager.ClipboardCollector", FakeCollector):
            manager.start()
            self.assertIsNotNone(manager._clipboard_collector)
            self.assertTrue(manager._clipboard_collector.running)
            manager.stop()


if __name__ == "__main__":
    unittest.main()
