"""Windows foreground-window duration collector; stores app/window metadata only."""
from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from ctypes import wintypes

logger = logging.getLogger("gigaam.observer.focus")


def _foreground():
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    title_buffer = ctypes.create_unicode_buffer(min(max(length + 1, 1), 2048))
    user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    title = title_buffer.value.strip()
    try:
        import psutil
        process = psutil.Process(pid.value)
        name = process.name()
        path = process.exe()
    except Exception:
        name, path = "unknown", None
    return {"hwnd": int(hwnd), "pid": int(pid.value), "name": name, "path": path, "title": title}


class FocusCollector:
    """Track which foreground app has focus and for how long."""

    def __init__(self, callback, interval: float = 1.0, provider=None, excluded=None):
        self.callback = callback
        self.interval = max(0.5, float(interval))
        self.provider = provider or _foreground
        self.excluded = {x.casefold() for x in (excluded or [])}
        self._stop = threading.Event()
        self._thread = None
        self._current = None
        self._since = None

    def scan_once(self):
        current = self.provider()
        if current:
            name = str(current.get("name") or "").casefold()
            path = str(current.get("path") or "").casefold()
            if name in self.excluded or path in self.excluded:
                current = None
        now = time.time()
        identity = None if current is None else (current.get("hwnd"), current.get("pid"))
        previous_identity = None if self._current is None else (self._current.get("hwnd"), self._current.get("pid"))
        if identity != previous_identity:
            self._flush(now)
            self._current = current
            self._since = now if current else None

    def _flush(self, ended_at):
        if not self._current or self._since is None:
            return
        duration = max(0.0, ended_at - self._since)
        if duration >= 1:
            data = self._current
            self.callback(
                category="focus", event_type="focus_session", source="foreground_window",
                object_name=data.get("name"), object_path=data.get("path"),
                details={
                    "pid": data.get("pid"),
                    "window_title": data.get("title", "")[:300],
                    "duration_seconds": round(duration, 1),
                },
            )

    def _run(self):
        try:
            while not self._stop.wait(self.interval):
                try:
                    self.scan_once()
                except Exception:
                    logger.exception("Foreground-window scan failed")
        finally:
            self._flush(time.time())
            self._current = None
            self._since = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="GigaAM-Observer-Focus", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.interval + 3)
        self._thread = None
