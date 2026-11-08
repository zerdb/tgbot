"""SQLite-backed multimedia notes and local attachment storage."""
from __future__ import annotations

import mimetypes
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from agent_core import APP_DATA

DB_PATH = APP_DATA / "multimedia_notes.db"
ATTACHMENTS_DIR = APP_DATA / "note_attachments"


@contextmanager
def _connect():
    APP_DATA.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id TEXT PRIMARY KEY,
            note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            caption TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    connection.commit()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def list_notes():
    with _connect() as db:
        rows = db.execute("""
            SELECT n.*, COUNT(a.id) AS attachment_count
            FROM notes n LEFT JOIN attachments a ON a.note_id = n.id
            GROUP BY n.id ORDER BY n.updated_at DESC
        """).fetchall()
        return [dict(row) for row in rows]


def get_note(note_id: str):
    with _connect() as db:
        row = db.execute("SELECT * FROM notes WHERE id = ?", (str(note_id),)).fetchone()
        if row is None:
            return None
        note = dict(row)
        note["attachments"] = [
            dict(item) for item in db.execute(
                "SELECT * FROM attachments WHERE note_id = ? ORDER BY created_at, id",
                (str(note_id),),
            ).fetchall()
        ]
        for item in note["attachments"]:
            item["path"] = str(ATTACHMENTS_DIR / item["stored_name"])
        return note


def save_note(note_id: str | None, title: str, body: str):
    title = str(title or "").strip() or "Новая заметка"
    body = str(body or "").strip()
    now = datetime.now().isoformat(timespec="seconds")
    note_id = str(note_id or uuid.uuid4().hex)
    with _connect() as db:
        exists = db.execute("SELECT 1 FROM notes WHERE id = ?", (note_id,)).fetchone()
        if exists:
            db.execute(
                "UPDATE notes SET title=?, body=?, updated_at=? WHERE id=?",
                (title, body, now, note_id),
            )
        else:
            db.execute(
                "INSERT INTO notes(id,title,body,created_at,updated_at) VALUES(?,?,?,?,?)",
                (note_id, title, body, now, now),
            )
    return note_id


def add_attachment(note_id: str, source_path: str | Path, caption: str = ""):
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"Файл не найден: {source}")
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    attachment_id = uuid.uuid4().hex
    suffix = source.suffix[:16]
    stored_name = attachment_id + suffix
    destination = ATTACHMENTS_DIR / stored_name
    shutil.copy2(source, destination)
    mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    try:
        with _connect() as db:
            if not db.execute("SELECT 1 FROM notes WHERE id=?", (str(note_id),)).fetchone():
                raise ValueError("Сначала сохраните заметку.")
            db.execute(
                """INSERT INTO attachments(id,note_id,filename,stored_name,mime_type,caption,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (attachment_id, str(note_id), source.name, stored_name, mime_type,
                 str(caption or "").strip(), datetime.now().isoformat(timespec="seconds")),
            )
            db.execute("UPDATE notes SET updated_at=? WHERE id=?",
                       (datetime.now().isoformat(timespec="seconds"), str(note_id)))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return attachment_id


def update_attachment_caption(attachment_id: str, caption: str):
    with _connect() as db:
        db.execute("UPDATE attachments SET caption=? WHERE id=?",
                   (str(caption or "").strip(), str(attachment_id)))


def delete_attachment(attachment_id: str):
    with _connect() as db:
        row = db.execute("SELECT stored_name FROM attachments WHERE id=?",
                         (str(attachment_id),)).fetchone()
        if row is None:
            return False
        db.execute("DELETE FROM attachments WHERE id=?", (str(attachment_id),))
    (ATTACHMENTS_DIR / row["stored_name"]).unlink(missing_ok=True)
    return True


def delete_note(note_id: str):
    note = get_note(note_id)
    if note is None:
        return False
    with _connect() as db:
        db.execute("DELETE FROM notes WHERE id=?", (str(note_id),))
    for item in note["attachments"]:
        (ATTACHMENTS_DIR / item["stored_name"]).unlink(missing_ok=True)
    return True
