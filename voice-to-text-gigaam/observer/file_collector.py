"""Polling file-system collector for explicitly selected user folders.

Records metadata only (path, filename, size and timestamps); never reads file contents.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger("gigaam.observer.files")


def _known_folder(guid_text: str) -> Path | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)
            ]

        import uuid
        value = uuid.UUID(guid_text)
        guid = GUID(value.time_low, value.time_mid, value.time_hi_version,
                    (ctypes.c_ubyte * 8)(*value.bytes[8:]))
        pointer = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(pointer)
        )
        if result != 0 or not pointer.value:
            return None
        path = Path(pointer.value)
        ctypes.windll.ole32.CoTaskMemFree(pointer)
        return path
    except Exception:
        logger.debug("Could not resolve Windows known folder %s", guid_text, exc_info=True)
        return None


def default_watch_folders() -> list[str]:
    """Resolve Desktop, Documents, Pictures and Downloads using Windows known folders."""
    ids = (
        "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",  # Desktop
        "FDD39AD0-238F-46AF-ADB4-6C85480369C7",  # Documents
        "33E28130-4E1E-4676-835A-98395C3BC3BB",  # Pictures
        "374DE290-123F-4565-9164-39C4925E467B",  # Downloads
    )
    folders = []
    for folder_id in ids:
        path = _known_folder(folder_id)
        if path and path.is_dir() and str(path) not in folders:
            folders.append(str(path))
    if not folders:
        home = Path.home()
        for name in ("Desktop", "Documents", "Pictures", "Downloads"):
            path = home / name
            if path.is_dir():
                folders.append(str(path))
    return folders


class FileCollector:
    def __init__(self, folders, callback, interval: float = 10.0):
        self.folders = [Path(p).expanduser().resolve() for p in folders if str(p).strip()]
        self.callback = callback
        self.interval = max(3.0, float(interval))
        self._stop = threading.Event()
        self._thread = None
        self._snapshot: dict[str, tuple[int, int, bool]] = {}

    def _scan(self) -> dict[str, tuple[int, int, bool]]:
        found = {}
        for root in self.folders:
            if not root.is_dir():
                logger.warning("Observer folder is unavailable: %s", root)
                continue
            for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(current) / d).is_symlink()]
                for name in files:
                    path = Path(current) / name
                    try:
                        if path.is_symlink():
                            continue
                        stat = path.stat()
                        found[str(path)] = (stat.st_size, stat.st_mtime_ns, False)
                    except (OSError, PermissionError):
                        continue
        return found

    def scan_once(self, initial: bool = False) -> int:
        current = self._scan()
        if initial:
            self._snapshot = current
            return 0
        old = self._snapshot
        count = 0
        for path, metadata in current.items():
            previous = old.get(path)
            if previous is None:
                event_type = "created"
            elif previous != metadata:
                event_type = "modified"
            else:
                continue
            p = Path(path)
            self.callback(
                category="files", event_type=event_type, source="filesystem",
                object_name=p.name, object_path=path,
                details={"size_bytes": metadata[0], "modified_ns": metadata[1]}
            )
            count += 1
        for path in old.keys() - current.keys():
            p = Path(path)
            self.callback(
                category="files", event_type="deleted", source="filesystem",
                object_name=p.name, object_path=path, details={}
            )
            count += 1
        self._snapshot = current
        return count

    def _run(self):
        self.scan_once(initial=True)
        while not self._stop.wait(self.interval):
            try:
                self.scan_once()
            except Exception:
                logger.exception("Observer file scan failed")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="GigaAM-Observer-Files", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.interval + 2)
        self._thread = None
