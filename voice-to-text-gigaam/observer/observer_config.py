"""Persistent, explicit opt-in configuration for GigaAM Observer."""
from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock

APP_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "GigaAMVoiceAssistant"
OBSERVER_DIR = APP_DIR / "observer"
CONFIG_PATH = OBSERVER_DIR / "config.json"

DEFAULT_CONFIG = {
    "enabled": False,
    "start_with_assistant": False,
    "retention": "forever",
    "analysis_schedule": "daily",
    "categories": {
        "files": False,
        "apps": False,
        "printing": False,
        "usb": False,
        "browser": False
    },
    "watched_folders": [],
    "excluded_folders": [],
    "excluded_processes": [],
    "created_with_consent": False
}

_lock = RLock()


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load config, filling new settings with safe defaults."""
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            save_config(DEFAULT_CONFIG, path)
            return json.loads(json.dumps(DEFAULT_CONFIG))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Configuration root must be an object")
        except (OSError, json.JSONDecodeError, ValueError):
            backup = path.with_suffix(".invalid.json")
            try:
                path.replace(backup)
            except OSError:
                pass
            save_config(DEFAULT_CONFIG, path)
            return json.loads(json.dumps(DEFAULT_CONFIG))

        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        merged.update({k: v for k, v in data.items() if k != "categories"})
        categories = data.get("categories", {})
        if isinstance(categories, dict):
            merged["categories"].update({
                k: bool(v) for k, v in categories.items()
                if k in merged["categories"]
            })
        for key in ("watched_folders", "excluded_folders", "excluded_processes"):
            if not isinstance(merged.get(key), list):
                merged[key] = []
        return merged


def save_config(config: dict, path: Path = CONFIG_PATH) -> None:
    """Atomically persist settings; never silently enable monitoring."""
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        if isinstance(config, dict):
            merged.update({k: v for k, v in config.items() if k != "categories"})
            categories = config.get("categories", {})
            if isinstance(categories, dict):
                merged["categories"].update({
                    k: bool(v) for k, v in categories.items()
                    if k in merged["categories"]
                })
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
