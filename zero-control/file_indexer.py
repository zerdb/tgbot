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


_LATIN_TO_CYRILLIC = str.maketrans({
    "a": "а", "b": "б", "c": "с", "d": "д", "e": "е", "f": "ф",
    "g": "г", "h": "х", "i": "и", "j": "ж", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "х",
    "y": "ы", "z": "з",
})
_CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
})


def _search_needle_variants(raw_query: str) -> list[str]:
    """Return normalized spelling variants for common Latin/Cyrillic ASR swaps."""
    normalized = unicodedata.normalize("NFKC", str(raw_query or "")).casefold().replace("ё", "е")
    needle = "".join(char for char in normalized if char.isalnum())
    if not needle:
        return []
    variants = [needle]
    has_latin = any("a" <= char <= "z" for char in needle)
    has_cyrillic = any("а" <= char <= "я" for char in needle)
    if has_latin and not has_cyrillic:
        alternate = needle.translate(_LATIN_TO_CYRILLIC)
    elif has_cyrillic and not has_latin:
        alternate = needle.translate(_CYRILLIC_TO_LATIN)
    else:
        alternate = needle
    if alternate and alternate != needle:
        variants.append(alternate)
    return variants


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
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.execute("PRAGMA busy_timeout=5000")
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
            char for char in unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё", "е")
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
    # Keep a normalized copy in the ordinary table as a fast C-level fallback.
    # Calling the Python SEARCHKEY UDF for every row made fallback searches take
    # minutes on large indexes when FTS5/trigram was unavailable.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(files)")}
    if "search_text" not in columns:
        connection.execute("ALTER TABLE files ADD COLUMN search_text TEXT NOT NULL DEFAULT ''")
    search_text_row = connection.execute(
        "SELECT value FROM index_meta WHERE key = 'search_text_version'"
    ).fetchone()
    if not search_text_row or search_text_row[0] != "1":
        with connection:
            connection.execute(
                "UPDATE files SET search_text = SEARCHKEY(name) || ' ' || SEARCHKEY(full_path)"
            )
            connection.execute(
                "INSERT OR REPLACE INTO index_meta(key, value) VALUES ('search_text_version', '1')"
            )
    # FTS5 trigram index supports fast substring search (including Cyrillic),
    # unlike instr(SEARCHKEY(...)), which scans every row.
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5("
            "drive UNINDEXED, full_path UNINDEXED, search_text, tokenize='trigram')"
        )
        fts_row = connection.execute("SELECT value FROM index_meta WHERE key = 'fts_populated'").fetchone()
        normalization_row = connection.execute(
            "SELECT value FROM index_meta WHERE key = 'fts_normalization_version'"
        ).fetchone()
        if not fts_row or not normalization_row or normalization_row[0] != "2":
            # SEARCHKEY now folds ё to е. Rebuild only the derived FTS table;
            # the existing MFT/SQLite file inventory remains untouched.
            with connection:
                connection.execute("DELETE FROM files_fts")
                connection.execute(
                    "INSERT INTO files_fts(drive, full_path, search_text) "
                    "SELECT drive, full_path, search_text FROM files"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO index_meta(key, value) VALUES ('fts_populated', '1')"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO index_meta(key, value) "
                    "VALUES ('fts_normalization_version', '2')"
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


def _search_file_rows(connection: sqlite3.Connection, needle: str) -> tuple[list[tuple], str]:
    """Search the normalized index, preferring trigram FTS and avoiding Python UDF scans."""
    fts_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'files_fts'"
    ).fetchone()
    if len(needle) >= 3 and fts_exists:
        try:
            fts_query = '"' + needle.replace('"', '""') + '"'
            rows = connection.execute(
                "SELECT full_path FROM files_fts WHERE files_fts MATCH ? LIMIT ?",
                (fts_query, MAX_RESULTS),
            ).fetchall()
            return rows, "FTS5 trigram"
        except sqlite3.OperationalError:
            # An incompatible SQLite build or damaged FTS table must not send
            # every row through the Python SEARCHKEY callback.
            rows = connection.execute(
                "SELECT full_path FROM files WHERE instr(search_text, ?) > 0 LIMIT ?",
                (needle, MAX_RESULTS),
            ).fetchall()
            return rows, "SQLite fallback (FTS5 error)"
    rows = connection.execute(
        "SELECT full_path FROM files WHERE instr(search_text, ?) > 0 LIMIT ?",
        (needle, MAX_RESULTS),
    ).fetchall()
    return rows, "SQLite fallback (FTS5 unavailable or query shorter than 3)"


def _search_index_query(connection: sqlite3.Connection, raw_query: str, report: Callable[[str], None] | None = None) -> list[Path]:
    """Run one text or metadata query against an already-open, already-refreshed index."""
    report = report or (lambda message: None)
    if raw_query.startswith("__EXT__:"):
        extension = raw_query.split(":", 1)[1].casefold()
        rows = connection.execute("SELECT full_path FROM files WHERE lower(full_path) LIKE ? LIMIT ?", ("%" + extension, MAX_RESULTS)).fetchall()
        return [Path(row[0]) for row in rows]
    if raw_query.startswith("__SIZE_RANGE__:"):
        _, lower_size, upper_size = raw_query.split(":", 2)
        rows = connection.execute("SELECT full_path FROM files WHERE size >= ? AND size < ? LIMIT ?", (int(lower_size), int(upper_size), MAX_RESULTS)).fetchall()
        return [Path(row[0]) for row in rows]
    if raw_query == "__ALL_FILTERED__":
        rows = connection.execute("SELECT full_path FROM files LIMIT 100000").fetchall()
        return [Path(row[0]) for row in rows]
    if raw_query in ("__SORT_SIZE_DESC__", "__SORT_SIZE_ASC__"):
        direction = "DESC" if raw_query == "__SORT_SIZE_DESC__" else "ASC"
        rows = connection.execute("SELECT full_path FROM files ORDER BY size " + direction + " LIMIT ?", (MAX_RESULTS,)).fetchall()
        return [Path(row[0]) for row in rows]
    needle_variants = _search_needle_variants(raw_query)
    if not needle_variants:
        rows = connection.execute("SELECT full_path FROM files ORDER BY name COLLATE NOCASE LIMIT ?", (MAX_RESULTS,)).fetchall()
        return [Path(row[0]) for row in rows]
    rows_by_path = {}
    for candidate_needle in needle_variants:
        candidate_started = time.perf_counter()
        rows, search_mode = _search_file_rows(connection, candidate_needle)
        report(f"[Тайминг] Вариант «{candidate_needle}»: {search_mode}; строк: {len(rows)}; {time.perf_counter() - candidate_started:.3f} сек.")
        rows_by_path.update((row[0], None) for row in rows)
    return [Path(path) for path in rows_by_path]

def refresh_and_search(query: str | list[str], report: Callable[[str], None] | None = None, force_refresh: bool = False) -> list[Path] | dict[str, list[Path]]:
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

    report("Открываю локальную базу SQLite и проверяю индекс файлов…")
    db_open_started = time.perf_counter()
    connection = _connect()
    report(f"[Тайминг] Открытие SQLite и подготовка индексов: {time.perf_counter() - db_open_started:.3f} сек.")
    refresh_started = time.perf_counter()
    scan_failures = []
    try:
        for drive in volumes:
            cached_count = connection.execute(
                "SELECT COUNT(*) FROM files WHERE drive = ?", (drive,)
            ).fetchone()[0]
            if cached_count and not force_refresh:
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
                scan_failures.append(f"{drive}: {exc}")
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
                    "INSERT INTO files(drive, full_path, name, size, search_text) "
                    "SELECT drive, full_path, name, size, "
                    "SEARCHKEY(name) || ' ' || SEARCHKEY(full_path) FROM scan_files"
                )
                try:
                    connection.execute("DELETE FROM files_fts WHERE drive = ?", (drive,))
                    connection.execute(
                        "INSERT INTO files_fts(drive, full_path, search_text) "
                        "SELECT drive, full_path, search_text FROM files WHERE drive = ?",
                        (drive,),
                    )
                except sqlite3.OperationalError:
                    pass
            report(f"{drive}: индексировано {count:,} файлов за {time.perf_counter() - started:.1f} сек.")
            try:
                from agent_core import load_settings, save_settings
                settings = load_settings()
                settings["mft_last_refresh_at"] = int(time.time())
                save_settings(settings)
            except Exception as exc:
                report(f"Не удалось сохранить время обновления индекса: {exc}")

        if query == "__INDEX_ONLY__":
            if scan_failures:
                raise RuntimeError("Не удалось обновить все доступные тома: " + "; ".join(scan_failures))
            return []

        if isinstance(query, (list, tuple)):
            # Пакетный режим: все варианты обслуживаются одним соединением SQLite.
            total = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            report(
                f"[Тайминг] Проверка сохранённого индекса: {time.perf_counter() - refresh_started:.3f} сек.; "
                f"всего записей: {total:,}."
            )
            batch_started = time.perf_counter()
            results: dict[str, list[Path]] = {}
            for raw_query in dict.fromkeys(str(item) for item in query if str(item).strip()):
                # Text and metadata queries share this connection and refresh pass.
                results[raw_query] = _search_index_query(connection, raw_query, report=report)
            report(
                f"[Тайминг] Выполнение {len(results)} поисковых вариантов: "
                f"{time.perf_counter() - batch_started:.3f} сек."
            )
            return results

        # Equivalent to *query*: find the text anywhere in the file name
        # or full path. casefold() makes matching case-insensitive for Cyrillic too.
        needle_variants = _search_needle_variants(query)
        needle = needle_variants[0] if needle_variants else ""
        if query.startswith("__EXT__:"):
            extension = query.split(":", 1)[1].casefold()
            rows = connection.execute(
                "SELECT full_path FROM files WHERE lower(full_path) LIKE ? LIMIT ?",
                ("%" + extension, MAX_RESULTS),
            ).fetchall()
            return [Path(row[0]) for row in rows]

        if query.startswith("__SIZE_RANGE__:"):
            _, lower_size, upper_size = query.split(":", 2)
            rows = connection.execute(
                "SELECT full_path FROM files WHERE size >= ? AND size < ? LIMIT ?",
                (int(lower_size), int(upper_size), MAX_RESULTS),
            ).fetchall()
            return [Path(row[0]) for row in rows]

        if query == "__ALL_FILTERED__":
            rows = connection.execute(
                "SELECT full_path FROM files LIMIT 100000"
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

        rows_by_path = {}
        # Search both original spelling and its likely cross-alphabet form.
        # This handles ASR output such as Latin "LPU" for Cyrillic "ЛПУ".
        for candidate_needle in needle_variants:
            candidate_started = time.perf_counter()
            rows, search_mode = _search_file_rows(connection, candidate_needle)
            report(
                f"[Тайминг] Вариант «{candidate_needle}»: {search_mode}; "
                f"строк: {len(rows)}; {time.perf_counter() - candidate_started:.3f} сек."
            )
            rows_by_path.update((row[0], None) for row in rows)
        rows = [(path,) for path in rows_by_path]

        if not rows:
            first_word = needle.split()[0] if " " in needle else needle[:3]
            partial = connection.execute(
                "SELECT name FROM files WHERE instr(search_text, ?) > 0 LIMIT 5",
                (first_word,),
            ).fetchall()
            if partial:
                examples = "; ".join(str(row[0]) for row in partial)
                report(f"Совпадения по части запроса «{first_word}»: {examples}")
            else:
                report(f"В именах файлов не найден даже фрагмент «{first_word}».")

        return [Path(row[0]) for row in rows]
    finally:
        close_started = time.perf_counter()
        connection.close()
        report(f"[Тайминг] Закрытие SQLite: {time.perf_counter() - close_started:.3f} сек.")


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
