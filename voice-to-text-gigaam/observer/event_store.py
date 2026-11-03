"""SQLite event history for GigaAM Observer (standard library only)."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


class EventStore:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self):
        connection = sqlite3.connect(str(self.database_path), timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self):
        with closing(self._connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS observer_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    object_name TEXT,
                    object_path TEXT,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    deduplication_key TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_observer_events_time
                ON observer_events(occurred_at)
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_observer_events_category_time
                ON observer_events(category, occurred_at)
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_observer_events_dedupe
                ON observer_events(deduplication_key, occurred_at)
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS observer_suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    pattern_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    user_response TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS observer_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    note TEXT NOT NULL,
                    related_event_id INTEGER,
                    FOREIGN KEY(related_event_id) REFERENCES observer_events(id)
                )
            """)
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def add_event(
        self,
        category: str,
        event_type: str,
        source: str,
        object_name: str | None = None,
        object_path: str | None = None,
        details: dict[str, Any] | None = None,
        occurred_at: str | None = None,
        deduplication_key: str | None = None,
    ) -> int | None:
        allowed = {"files", "apps", "printing", "usb", "browser", "voice"}
        if category not in allowed:
            raise ValueError(f"Unsupported event category: {category}")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        occurred_at = occurred_at or now
        payload = json.dumps(details or {}, ensure_ascii=False, separators=(",", ":"))
        with closing(self._connect()) as db, db:
            if deduplication_key:
                exists = db.execute(
                    """SELECT id FROM observer_events
                       WHERE deduplication_key=? AND occurred_at>=datetime(?, '-3 seconds')
                       ORDER BY id DESC LIMIT 1""",
                    (deduplication_key, occurred_at),
                ).fetchone()
                if exists:
                    return None
            cursor = db.execute(
                """INSERT INTO observer_events
                   (occurred_at, category, event_type, source, object_name,
                    object_path, details_json, deduplication_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (occurred_at, category, event_type, source, object_name,
                 object_path, payload, deduplication_key, now),
            )
            return int(cursor.lastrowid)

    def add_note(self, note: str, related_event_id: int | None = None) -> int:
        cleaned = note.strip()
        if not cleaned:
            raise ValueError("Note cannot be empty")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(self._connect()) as db, db:
            cursor = db.execute(
                "INSERT INTO observer_notes(created_at, note, related_event_id) VALUES (?, ?, ?)",
                (now, cleaned, related_event_id),
            )
            return int(cursor.lastrowid)

    def list_events(self, limit: int = 100, category: str | None = None) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        query = "SELECT * FROM observer_events"
        params: list[Any] = []
        if category:
            query += " WHERE category=?"
            params.append(category)
        query += " ORDER BY occurred_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with closing(self._connect()) as db, db:
            rows = db.execute(query, params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            result.append(item)
        return result

    def count_events(self) -> int:
        with closing(self._connect()) as db, db:
            return int(db.execute("SELECT COUNT(*) FROM observer_events").fetchone()[0])
