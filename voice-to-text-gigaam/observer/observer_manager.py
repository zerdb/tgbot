"""Lifecycle and public API for GigaAM Observer."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from .event_store import EventStore
from .file_collector import FileCollector, default_watch_folders
from .process_collector import ProcessCollector
from .focus_collector import FocusCollector
from .clipboard_collector import ClipboardCollector
from .observer_config import OBSERVER_DIR, load_config, save_config
from .pattern_analyzer import analyze_patterns

logger = logging.getLogger("gigaam.observer")


class ObserverManager:
    """Owns Observer configuration and storage; collectors are added in later stages."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else OBSERVER_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config = load_config(self.data_dir / "config.json")
        self.store = EventStore(self.data_dir / "observer.sqlite3")
        if not self.config.get("watched_folders"):
            self.config["watched_folders"] = default_watch_folders()
            save_config(self.config, self.data_dir / "config.json")
        self.started = False
        self._file_collector = None
        self._process_collector = None
        self._focus_collector = None
        self._clipboard_collector = None

    @property
    def is_enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    def start(self) -> bool:
        """Start only after explicit opt-in; currently initializes the safe core."""
        if not self.is_enabled:
            logger.info("Observer is disabled; no activity is being collected.")
            return False
        self.started = True
        if self.config.get("categories", {}).get("files", False):
            folders = self.config.get("watched_folders", [])
            if folders:
                self._file_collector = FileCollector(folders, self.record_event)
                self._file_collector.start()
                logger.info("File collector started for %d selected folders.", len(folders))
            else:
                logger.warning("File monitoring is enabled but no folders are selected.")
        if self.config.get("categories", {}).get("apps", False):
            self._process_collector = ProcessCollector(
                self.record_event,
                excluded_processes=self.config.get("excluded_processes", []),
            )
            self._process_collector.start()
            logger.info("Process collector started.")

        categories = self.config.get("categories", {})
        excluded = self.config.get("excluded_processes", [])
        if categories.get("focus", False):
            self._focus_collector = FocusCollector(self.record_event, excluded=excluded)
            self._focus_collector.start()
            logger.info("Foreground focus collector started.")
        if categories.get("clipboard", False):
            self._clipboard_collector = ClipboardCollector(self.record_event)
            self._clipboard_collector.start()
            logger.info("Protected clipboard collector started.")
        logger.info("Observer core started.")
        return True

    def analyze_now(self, days: int = 7) -> int:
        """Run deterministic local analysis; no network or raw data leaves the PC."""
        patterns = analyze_patterns(self.store, days=days)
        created = self.store.save_suggestions(patterns)
        logger.info("Observer analysis found %d new suggestions.", created)
        return created

    def stop(self) -> None:
        self.started = False
        if self._file_collector:
            self._file_collector.stop()
            self._file_collector = None
        if self._process_collector:
            self._process_collector.stop()
            self._process_collector = None
        if self._focus_collector:
            self._focus_collector.stop()
            self._focus_collector = None
        if self._clipboard_collector:
            self._clipboard_collector.stop()
            self._clipboard_collector = None

    def record_event(self, category: str, event_type: str, source: str,
                     object_name: str | None = None, object_path: str | None = None,
                     details: dict | None = None, deduplication_key: str | None = None):
        if not self.started:
            return None
        if category != "voice" and not self.config.get("categories", {}).get(category, False):
            return None
        return self.store.add_event(
            category=category,
            event_type=event_type,
            source=source,
            object_name=object_name,
            object_path=object_path,
            details=details,
            deduplication_key=deduplication_key,
        )
