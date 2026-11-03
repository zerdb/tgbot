"""Lifecycle and public API for GigaAM Observer."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from .event_store import EventStore
from .observer_config import OBSERVER_DIR, load_config

logger = logging.getLogger("gigaam.observer")


class ObserverManager:
    """Owns Observer configuration and storage; collectors are added in later stages."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else OBSERVER_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config = load_config(self.data_dir / "config.json")
        self.store = EventStore(self.data_dir / "observer.sqlite3")
        self.started = False

    @property
    def is_enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    def start(self) -> bool:
        """Start only after explicit opt-in; currently initializes the safe core."""
        if not self.is_enabled:
            logger.info("Observer is disabled; no activity is being collected.")
            return False
        self.started = True
        logger.info("Observer core initialized. Event collectors are not yet enabled.")
        return True

    def stop(self) -> None:
        self.started = False

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
