"""Opt-in clipboard text monitor with conservative secret redaction."""
from __future__ import annotations

import ctypes
import logging
import os
import re
import threading
import hashlib

logger = logging.getLogger("gigaam.observer.clipboard")

_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|пароль|token|api[_ -]?key|secret)\s*[:=]\s*\S+"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
]


def redact_sensitive(text: str) -> str | None:
    """Return safe text, or None when a likely credential/secret is present."""
    value = text.strip()
    if not value:
        return None
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        return None
    if len(value) > 12000:
        return None
    return value


def _read_clipboard_text():
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    if not user32.OpenClipboard(None):
        return None
    handle = None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


class ClipboardCollector:
    """Poll clipboard sequence number and store changed text after redaction."""
    def __init__(self, callback, interval: float = 1.0, reader=None, sequence_provider=None):
        self.callback = callback
        self.interval = max(0.5, float(interval))
        self.reader = reader or _read_clipboard_text
        self.sequence_provider = sequence_provider or self._sequence
        self._last_sequence = None
        self._last_hash = None
        self._stop = threading.Event()
        self._thread = None

    @staticmethod
    def _sequence():
        if os.name != "nt":
            return None
        return int(ctypes.windll.user32.GetClipboardSequenceNumber())

    def scan_once(self):
        sequence = self.sequence_provider()
        if sequence is None or sequence == self._last_sequence:
            return False
        self._last_sequence = sequence
        raw = self.reader()
        if not isinstance(raw, str):
            return False
        safe = redact_sensitive(raw)
        if safe is None:
            return False
        digest = hashlib.sha256(safe.encode("utf-8")).hexdigest()
        if digest == self._last_hash:
            return False
        self._last_hash = digest
        self.callback(
            category="clipboard", event_type="text_copied", source="windows_clipboard",
            object_name=f"{len(safe)} символов",
            details={"text": safe, "sha256": digest},
        )
        return True

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.scan_once()
            except Exception:
                logger.exception("Clipboard monitor failed")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="GigaAM-Observer-Clipboard", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.interval + 2)
        self._thread = None
