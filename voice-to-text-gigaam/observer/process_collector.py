"""Opt-in process lifecycle collector.

Records process names and executable paths only. It never reads command lines,
window titles, keystrokes, memory, or process contents.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

logger = logging.getLogger("gigaam.observer.processes")


def _system_processes():
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("Process monitoring requires psutil; install project requirements.") from exc

    result = {}
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            info = process.info
            pid = int(info["pid"])
            name = str(info.get("name") or "unknown")
            executable = info.get("exe")
            result[pid] = {
                "name": name,
                "path": str(Path(executable)) if executable else None,
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError, TypeError, ValueError):
            continue
    return result


class ProcessCollector:
    """Poll process metadata and emit started/stopped events."""

    def __init__(self, callback, interval: float = 3.0, excluded_processes=None,
                 process_provider=None):
        self.callback = callback
        self.interval = max(1.0, float(interval))
        self.excluded_processes = {
            str(item).casefold() for item in (excluded_processes or []) if str(item).strip()
        }
        self.process_provider = process_provider or _system_processes
        self._snapshot = {}
        self._stop = threading.Event()
        self._thread = None

    def _filtered_snapshot(self):
        current = self.process_provider()
        return {
            pid: data for pid, data in current.items()
            if str(data.get("name") or "").casefold() not in self.excluded_processes
            and (str(data.get("path") or "").casefold() not in self.excluded_processes)
        }

    def scan_once(self, initial: bool = False) -> int:
        current = self._filtered_snapshot()
        if initial:
            self._snapshot = current
            return 0
        count = 0
        for pid, data in current.items():
            if pid not in self._snapshot:
                self.callback(
                    category="apps", event_type="started", source="process",
                    object_name=data["name"], object_path=data.get("path"),
                    details={"pid": pid},
                )
                count += 1
        for pid, data in self._snapshot.items():
            if pid not in current:
                self.callback(
                    category="apps", event_type="stopped", source="process",
                    object_name=data["name"], object_path=data.get("path"),
                    details={"pid": pid},
                )
                count += 1
        self._snapshot = current
        return count

    def _run(self):
        try:
            self.scan_once(initial=True)
            while not self._stop.wait(self.interval):
                try:
                    self.scan_once()
                except Exception:
                    logger.exception("Observer process scan failed")
        except Exception:
            logger.exception("Observer process collector could not start")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="GigaAM-Observer-Processes", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.interval + 2)
        self._thread = None
