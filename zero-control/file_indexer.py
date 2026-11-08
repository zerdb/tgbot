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
from agent_core import APP_DATA
from typing import Callable


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
    # Реальный формат mftparser 1.7.x (проверен на Windows):
    # 0=MFT record, 3=parent reference, 4=parent record,
    # 6=active, 7=path, 8=name, 9=size, 11=is_directory.
    if len(entry) < 12:
        return None
    if not entry[6] or entry[11]:
        return None

    relative_path = str(entry[7] or "").strip().replace("/", "\\")
    name = str(entry[8] or "").strip()
    if not relative_path or not name or name in (".", ".."):
        return None

    # Поле 7 уже содержит путь от корня тома вместе с именем файла.
    relative_path = relative_path.lstrip("\\")
    full_path = os.path.normpath(drive + "\\\\" + relative_path)

    try:
        size = max(0, int(entry[9] or 0))
    except (TypeError, ValueError):
        size = 0
    return full_path, name, size


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
    connection.execute(
        "CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    # FTS5 trigram index supports fast substring search (including Cyrillic),
    # unlike instr(SEARCHKEY(...)), which scans every row.
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5("
            "drive UNINDEXED, full_path UNINDEXED, search_text, tokenize='trigram')"
        )
        fts_row = connection.execute("SELECT value FROM index_meta WHERE key = 'fts_populated'").fetchone()
        if not fts_row:
            with connection:
                connection.execute("DELETE FROM files_fts")
                connection.execute(
                    "INSERT INTO files_fts(drive, full_path, search_text) "
                    "SELECT drive, full_path, "
                    "SEARCHKEY(name) || ' ' || SEARCHKEY(full_path) FROM files"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO index_meta(key, value) VALUES ('fts_populated', '1')"
                )
    except sqlite3.OperationalError:
        # Fallback below remains compatible with SQLite builds without FTS5/trigram.
        pass
    version_row = connection.execute(
        "SELECT value FROM index_meta WHERE key = 'schema_version'"
    ).fetchone()
    if not version_row or version_row[0] != "2":
        # Старые записи были построены по неверным индексам кортежа MFT.
        # Их нельзя использовать: пути и количество файлов недостоверны.
        with connection:
            connection.execute("DELETE FROM files")
            connection.execute(
                "INSERT OR REPLACE INTO index_meta(key, value) VALUES ('schema_version', '2')"
            )
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
                try:
                    connection.execute("DELETE FROM files_fts WHERE drive = ?", (drive,))
                    connection.execute(
                        "INSERT INTO files_fts(drive, full_path, search_text) "
                        "SELECT drive, full_path, "
                        "SEARCHKEY(name) || ' ' || SEARCHKEY(full_path) "
                        "FROM scan_files"
                    )
                except sqlite3.OperationalError:
                    pass
            report(f"{drive}: индексировано {count:,} файлов за {time.perf_counter() - started:.1f} сек.")

        # Equivalent to *query*: find the text anywhere in the file name
        # or full path. casefold() makes matching case-insensitive for Cyrillic too.
        needle = "".join(
            char for char in unicodedata.normalize("NFKC", query).casefold()
            if char.isalnum()
        )
        if query.startswith("__EXT__:"):
            extension = query.split(":", 1)[1].casefold()
            rows = connection.execute(
                "SELECT full_path FROM files WHERE lower(full_path) LIKE ? LIMIT ?",
                ("%" + extension, MAX_RESULTS),
            ).fetchall()
            return [Path(row[0]) for row in rows]

        if query in ("__SORT_SIZE_DESC__", "__SORT_SIZE_ASC__"):
            direction = "DESC" if query == "__SORT_SIZE_DESC__" else "ASC"
            rows = connection.execute(
                "SELECT full_path FROM files ORDER BY size " + direction + " LIMIT ?",
                (MAX_RESULTS,),
            ).fetchall()
            return [Path(row[0]) for row in rows]

        if not needle:
            # Пустая строка означает запрос только по фильтрам: типу, дате,
            # диску или расположению. Фильтрация выполняется в file_search.py.
            rows = connection.execute(
                "SELECT full_path FROM files ORDER BY name COLLATE NOCASE LIMIT ?",
                (MAX_RESULTS,),
            ).fetchall()
            return [Path(row[0]) for row in rows]

        total = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        report(f"В базе SQLite записей: {total:,}. Ищу нормализованную строку «{needle}»...")

        rows = []
        # Trigram FTS is indexed and finds a substring without scanning the
        # entire SQLite table. For 1-2 character queries use the safe fallback.
        if len(needle) >= 3:
            try:
                fts_query = '"' + needle.replace('"', '""') + '"'
                rows = connection.execute(
                    "SELECT full_path FROM files_fts "
                    "WHERE files_fts MATCH ? LIMIT ?",
                    (fts_query, MAX_RESULTS),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []

        if not rows and len(needle) < 3:
            rows = connection.execute(
                "SELECT full_path FROM files "
                "WHERE instr(SEARCHKEY(name), ?) > 0 "
                "OR instr(SEARCHKEY(full_path), ?) > 0 LIMIT ?",
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


def refresh_and_search_folders(query: str, report: Callable[[str], None] | None = None) -> list[Path]:
    """Index active NTFS directories in SQLite and find folders by name/path."""
    report = report or (lambda message: print(message, flush=True))
    if not is_admin():
        raise PermissionError(
            "Для чтения MFT нужны права администратора. Закройте программу и запустите "
            "PyCharm от имени администратора, затем снова запустите проект."
        )
    try:
        import mftparser
    except ImportError as exc:
        raise RuntimeError("Не установлена библиотека mftparser. Обновите requirements.txt.") from exc

    needle = "".join(
        char for char in unicodedata.normalize("NFKC", str(query or "")).casefold()
        if char.isalnum()
    )
    if not needle:
        return []

    volumes = _available_ntfs_volumes()
    if not volumes:
        raise OSError("Не найдены доступные диски.")

    connection = _connect()
    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                drive TEXT NOT NULL,
                full_path TEXT NOT NULL,
                name TEXT NOT NULL
            )
        """)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_folders_name ON folders(name COLLATE NOCASE)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_folders_drive ON folders(drive)")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS folder_scans (
                drive TEXT PRIMARY KEY,
                scanned_at REAL NOT NULL
            )
        """)
        fts_available = True
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS folders_fts USING fts5("
                "drive UNINDEXED, full_path UNINDEXED, search_text, tokenize='trigram')"
            )
        except sqlite3.OperationalError:
            fts_available = False

        for drive in volumes:
            scanned = connection.execute(
                "SELECT 1 FROM folder_scans WHERE drive = ?", (drive,)
            ).fetchone()
            if scanned:
                continue
            report(f"Индексирую папки {drive} через MFT...")
            started = time.perf_counter()
            try:
                entries = mftparser.ScanVolume(drive, only_active=True)
                connection.execute(
                    "CREATE TEMP TABLE IF NOT EXISTS scan_folders "
                    "(drive TEXT, full_path TEXT, name TEXT)"
                )
                connection.execute("DELETE FROM scan_folders")
                batch = []
                count = 0
                for entry in entries:
                    if len(entry) < 12 or not entry[6] or not entry[11]:
                        continue
                    relative_path = str(entry[7] or "").strip().replace("/", "\\").lstrip("\\")
                    name = str(entry[8] or "").strip()
                    if not relative_path or not name or name in (".", ".."):
                        continue
                    full_path = os.path.normpath(drive + "\\\\" + relative_path)
                    batch.append((drive, full_path, name))
                    if len(batch) >= BATCH_SIZE:
                        connection.executemany(
                            "INSERT INTO scan_folders(drive, full_path, name) VALUES (?, ?, ?)", batch
                        )
                        count += len(batch)
                        batch.clear()
                        report(f"{drive}: подготовлено {count:,} папок...")
                if batch:
                    connection.executemany(
                        "INSERT INTO scan_folders(drive, full_path, name) VALUES (?, ?, ?)", batch
                    )
                    count += len(batch)
                with connection:
                    connection.execute("DELETE FROM folders WHERE drive = ?", (drive,))
                    connection.execute(
                        "INSERT INTO folders(drive, full_path, name) "
                        "SELECT drive, full_path, name FROM scan_folders"
                    )
                    if fts_available:
                        connection.execute("DELETE FROM folders_fts WHERE drive = ?", (drive,))
                        connection.execute(
                            "INSERT INTO folders_fts(drive, full_path, search_text) "
                            "SELECT drive, full_path, SEARCHKEY(name) || ' ' || SEARCHKEY(full_path) "
                            "FROM scan_folders"
                        )
                    connection.execute(
                        "INSERT OR REPLACE INTO folder_scans(drive, scanned_at) VALUES (?, ?)",
                        (drive, time.time()),
                    )
                report(f"{drive}: индексировано {count:,} папок за {time.perf_counter() - started:.1f} сек.")
            except Exception as exc:
                report(f"Не удалось проиндексировать папки {drive}: {exc}")

        rows = []
        if fts_available and len(needle) >= 3:
            try:
                rows = connection.execute(
                    "SELECT full_path FROM folders_fts WHERE folders_fts MATCH ? LIMIT ?",
                    ('"' + needle.replace('"', '""') + '"', MAX_RESULTS),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        if not rows:
            rows = connection.execute(
                "SELECT full_path FROM folders "
                "WHERE instr(SEARCHKEY(name), ?) > 0 "
                "OR instr(SEARCHKEY(full_path), ?) > 0 LIMIT ?",
                (needle, needle, MAX_RESULTS),
            ).fetchall()

        paths = []
        seen = set()
        for row in rows:
            path = Path(row[0])
            key = str(path).casefold()
            if key not in seen and path.is_dir():
                seen.add(key)
                paths.append(path)
        paths.sort(key=lambda path: (
            0 if path.name.casefold() == str(query).casefold() else 1,
            len(str(path)),
            str(path).casefold(),
        ))
        report(f"Найдено существующих папок: {len(paths)}.")
        return paths[:MAX_RESULTS]
    finally:
        connection.close()
