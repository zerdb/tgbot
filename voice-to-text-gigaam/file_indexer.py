"""Fast NTFS file index based on the Master File Table (MFT) and SQLite.

MFT access requires an elevated Windows process. The index is refreshed from
each NTFS volume before a search; successful volume scans replace only that
volume's rows in a transaction, so a failed scan never destroys its old index.
"""
from __future__ import annotations

import ctypes
import os
import sqlite3
import string
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Callable

APP_DATA = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "GigaAMVoiceAssistant"
DB_PATH = APP_DATA / "file_index.sqlite3"
BATCH_SIZE = 50_000
MAX_RESULTS = 1000


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _available_ntfs_volumes() -> list[str]:
    """Return mounted drive letters; mftparser will reject non-NTFS volumes."""
    if os.name != "nt":
        raise OSError("MFT-поиск доступен только в Windows.")
    drives = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        if root.exists():
            drives.append(f"{letter}:")
    return drives


def _entry_to_path(drive: str, entry) -> tuple[str, str, int] | None:
    # mftparser 1.7.x tuple layout:
    # path=5, name=6, size=7, is_dir=9. (В присланном примере индексы
    # path/size сдвинуты: entry[7] — это размер, entry[9] — флаг папки.)
    if len(entry) <= 9:
        return None
    relative_path = entry[5]
    name = entry[6]
    size = entry[7]
    is_dir = entry[9]
    if is_dir or not name:
        return None

    relative_path = str(relative_path or "").strip()
    name = str(name).strip()
    if not name:
        return None

    if len(relative_path) >= 2 and relative_path[1] == ":":
        full_path = relative_path
        if Path(full_path).name.casefold() != name.casefold():
            full_path = os.path.join(full_path, name)
    else:
        relative_path = relative_path.replace("/", "\\")
        if relative_path.startswith("\\"):
            full_path = drive + relative_path
        elif relative_path:
            full_path = drive + "\\" + relative_path.lstrip("\\")
        else:
            full_path = drive + "\\"
        if Path(full_path).name.casefold() != name.casefold():
            full_path = os.path.join(full_path, name)

    try:
        size = max(0, int(size or 0))
    except (TypeError, ValueError):
        size = 0
    return os.path.normpath(full_path), name, size


def _connect() -> sqlite3.Connection:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA temp_store=MEMORY")
    # Python casefold() provides Unicode-aware, case-insensitive matching,
    # including Cyrillic (SQLite's built-in NOCASE handles ASCII only).
    connection.create_function(
        "CASEFOLD", 1,
        lambda value: unicodedata.normalize("NFKC", str(value or "")).casefold(),
        deterministic=True,
    )
    # Игнорируем пробелы и разделители: «акт сверки», «акт-сверки»
    # и «акт_сверки» должны находиться одинаково.
    connection.create_function(
        "SEARCHKEY", 1,
        lambda value: "".join(
            char for char in unicodedata.normalize("NFKC", str(value or "")).casefold()
            if char.isalnum()
        ),
        deterministic=True,
    )
    connection.execute("""
        CREATE TABLE IF NOT EXISTS files (
            drive TEXT NOT NULL,
            full_path TEXT NOT NULL,
            name TEXT NOT NULL,
            size INTEGER NOT NULL DEFAULT 0
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_files_name ON files(name COLLATE NOCASE)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(full_path COLLATE NOCASE)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_files_drive ON files(drive)")
    return connection


def refresh_and_search(query: str, report: Callable[[str], None] | None = None) -> list[Path]:
    """Refresh available NTFS volumes and return matching file paths."""
    report = report or (lambda message: print(message, flush=True))
    if not is_admin():
        raise PermissionError(
            "Для чтения MFT нужны права администратора. Закройте программу и запустите "
            "PyCharm от имени администратора, затем снова запустите проект."
        )

    try:
        import mftparser  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Не установлена библиотека mftparser. Обновите requirements.txt.") from exc

    volumes = _available_ntfs_volumes()
    if not volumes:
        raise OSError("Не найдены доступные диски.")

    connection = _connect()
    try:
        for drive in volumes:
            cached_count = connection.execute(
                "SELECT COUNT(*) FROM files WHERE drive = ?", (drive,)
            ).fetchone()[0]
            if cached_count:
                report(
                    f"Использую сохранённый индекс {drive}: "
                    f"{cached_count:,} файлов (повторное сканирование не требуется)."
                )
                continue

            report(f"Индексирую {drive} через MFT...")
            started = time.perf_counter()
            try:
                entries = mftparser.ScanVolume(drive, only_active=True)
            except Exception as exc:
                report(f"Пропускаю {drive}: MFT недоступна ({exc}).")
                continue

            connection.execute("CREATE TEMP TABLE IF NOT EXISTS scan_files "
                               "(drive TEXT, full_path TEXT, name TEXT, size INTEGER)")
            connection.execute("DELETE FROM scan_files")
            batch = []
            count = 0
            for entry in entries:
                parsed = _entry_to_path(drive, entry)
                if parsed:
                    full_path, name, size = parsed
                    batch.append((drive, full_path, name, size))
                if len(batch) >= BATCH_SIZE:
                    connection.executemany(
                        "INSERT INTO scan_files(drive, full_path, name, size) VALUES (?, ?, ?, ?)",
                        batch,
                    )
                    count += len(batch)
                    batch.clear()
                    report(f"{drive}: подготовлено {count:,} файлов...")
            if batch:
                connection.executemany(
                    "INSERT INTO scan_files(drive, full_path, name, size) VALUES (?, ?, ?, ?)",
                    batch,
                )
                count += len(batch)

            # Swap only after a complete successful scan.
            with connection:
                connection.execute("DELETE FROM files WHERE drive = ?", (drive,))
                connection.execute(
                    "INSERT INTO files(drive, full_path, name, size) "
                    "SELECT drive, full_path, name, size FROM scan_files"
                )
            report(f"{drive}: индексировано {count:,} файлов за {time.perf_counter() - started:.1f} сек.")

        # Equivalent to *query*: find the text anywhere in the file name
        # or full path. casefold() makes matching case-insensitive for Cyrillic too.
        needle = "".join(
            char for char in unicodedata.normalize("NFKC", query).casefold()
            if char.isalnum()
        )
        if not needle:
            return []

        total = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        report(f"В базе SQLite записей: {total:,}. Ищу нормализованную строку «{needle}»...")

        rows = connection.execute(
            "SELECT full_path FROM files "
            "WHERE instr(SEARCHKEY(name), ?) > 0 "
            "OR instr(SEARCHKEY(full_path), ?) > 0 "
            "ORDER BY SEARCHKEY(name) LIMIT ?",
            (needle, needle, MAX_RESULTS),
        ).fetchall()

        if not rows:
            first_word = needle.split()[0] if " " in needle else needle[:3]
            partial = connection.execute(
                "SELECT name FROM files WHERE instr(SEARCHKEY(name), ?) > 0 LIMIT 5",
                (first_word,),
            ).fetchall()
            if partial:
                examples = "; ".join(str(row[0]) for row in partial)
                report(f"Совпадения по части запроса «{first_word}»: {examples}")
            else:
                report(f"В именах файлов не найден даже фрагмент «{first_word}».")

        return [Path(row[0]) for row in rows]
    finally:
        connection.close()
