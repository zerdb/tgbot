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
        allowed = {"files", "apps", "focus", "clipboard", "printing", "usb", "browser", "voice"}
        if category not in allowed:
            raise ValueError(f"Unsupported event category: {category}")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        occurred_at = occurred_at or now
        incoming = dict(details or {})
        with closing(self._connect()) as db, db:
            # Keep one rolling row per app, and one rolling clipboard row.
            if category in {"focus", "apps", "clipboard", "files"}:
                key_name = (object_path if category == "files" else (object_name or category)) or ""
                key_name = key_name.casefold()
                if category == "files":
                    row = db.execute(
                        """SELECT id, occurred_at, details_json, event_type, object_path
                           FROM observer_events
                           WHERE category=? AND lower(coalesce(object_path, ''))=?
                           ORDER BY id DESC LIMIT 1""",
                        (category, key_name),
                    ).fetchone()
                else:
                    row = db.execute(
                        """SELECT id, occurred_at, details_json, event_type, object_path
                           FROM observer_events
                           WHERE category=? AND lower(coalesce(object_name, ''))=?
                           ORDER BY id DESC LIMIT 1""",
                        (category, key_name),
                    ).fetchone()
                if row:
                    old = json.loads(row["details_json"] or "{}")
                    if category == "files":
                        old["changes"] = int(old.get("changes", 1) or 1) + 1
                        old["last_change"] = event_type
                        old["last_size_bytes"] = incoming.get("size_bytes", old.get("last_size_bytes"))
                        old["last_modified_ns"] = incoming.get("modified_ns", old.get("last_modified_ns"))
                    elif category == "focus":
                        old_seconds = float(old.get("duration_seconds", 0) or 0)
                        new_seconds = float(incoming.get("duration_seconds", 0) or 0)
                        old["duration_seconds"] = round(old_seconds + new_seconds, 1)
                        old["sessions"] = int(old.get("sessions", 0) or 0) + 1
                        titles = old.setdefault("window_titles", [])
                        title = incoming.get("window_title")
                        if title and title not in titles:
                            titles.append(title)
                        old["last_pid"] = incoming.get("pid", old.get("last_pid"))
                    elif category == "apps":
                        counter = "starts" if event_type == "started" else "stops"
                        old[counter] = int(old.get(counter, 0) or 0) + 1
                        old["last_pid"] = incoming.get("pid", old.get("last_pid"))
                    else:
                        history = old.setdefault("history", [])
                        text_value = incoming.get("text")
                        digest = incoming.get("sha256")
                        if text_value and (not history or history[-1].get("sha256") != digest):
                            history.append({
                                "copied_at": occurred_at,
                                "text": text_value,
                                "sha256": digest,
                            })
                        old["text"] = text_value or old.get("text", "")
                        old["sha256"] = digest or old.get("sha256")
                        old["copies"] = len(history)
                    db.execute(
                        """UPDATE observer_events
                           SET occurred_at=?, event_type=?, source=?, object_path=?,
                               details_json=?, created_at=?
                           WHERE id=?""",
                        (occurred_at, event_type, source, object_path or row["object_path"],
                         json.dumps(old, ensure_ascii=False, separators=(",", ":")),
                         now, row["id"]),
                    )
                    return int(row["id"])

                if category == "files":
                    incoming["changes"] = 1
                    incoming["last_change"] = event_type
                    incoming["last_size_bytes"] = incoming.get("size_bytes")
                    incoming["last_modified_ns"] = incoming.get("modified_ns")
                elif category == "focus":
                    incoming["sessions"] = 1
                elif category == "apps":
                    incoming["starts"] = 1 if event_type == "started" else 0
                    incoming["stops"] = 1 if event_type == "stopped" else 0
                elif category == "clipboard":
                    text_value = incoming.get("text")
                    incoming["history"] = [{
                        "copied_at": occurred_at,
                        "text": text_value,
                        "sha256": incoming.get("sha256"),
                    }] if text_value else []
                    incoming["copies"] = len(incoming["history"])

            payload = json.dumps(incoming, ensure_ascii=False, separators=(",", ":"))
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


    def save_suggestions(self, suggestions: list[dict]) -> int:
        """Insert new pattern suggestions without overwriting user decisions."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        inserted = 0
        with closing(self._connect()) as db, db:
            for item in suggestions:
                cursor = db.execute(
                    """INSERT OR IGNORE INTO observer_suggestions
                       (created_at, title, description, pattern_key, status)
                       VALUES (?, ?, ?, ?, 'pending')""",
                    (now, item["title"], item["description"], item["pattern_key"]),
                )
                inserted += max(0, cursor.rowcount)
        return inserted

    def list_suggestions(self, status: str | None = None, limit: int = 200) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        query = "SELECT * FROM observer_suggestions"
        params: list[Any] = []
        if status:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with closing(self._connect()) as db, db:
            return [dict(row) for row in db.execute(query, params).fetchall()]

    def update_suggestion(self, suggestion_id: int, status: str, response: str | None = None) -> bool:
        if status not in {"accepted", "dismissed", "pending"}:
            raise ValueError("Unsupported suggestion status")
        with closing(self._connect()) as db, db:
            cursor = db.execute(
                "UPDATE observer_suggestions SET status=?, user_response=? WHERE id=?",
                (status, response, int(suggestion_id)),
            )
            return cursor.rowcount > 0

    def clear_history(self) -> None:
        """Delete all event history, saved suggestions, and manual notes."""
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM observer_notes")
            db.execute("DELETE FROM observer_suggestions")
            db.execute("DELETE FROM observer_events")
            db.execute("DELETE FROM sqlite_sequence WHERE name IN "
                       "('observer_events', 'observer_suggestions', 'observer_notes')")

    def count_events(self) -> int:
        with closing(self._connect()) as db, db:
            return int(db.execute("SELECT COUNT(*) FROM observer_events").fetchone()[0])
