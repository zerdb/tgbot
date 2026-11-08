"""Поиск и запуск установленных приложений Windows по названию."""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import time
from pathlib import Path


_APP_CACHE = []
_CACHE_TIME = 0.0
_CACHE_TTL = 60.0


def _normalize(value: str) -> str:
    value = str(value or "").casefold().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    return " ".join(value.split())


def _shortcut_roots() -> list[Path]:
    roots = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    userprofile = os.environ.get("USERPROFILE")
    public = os.environ.get("PUBLIC")
    if appdata:
        roots.append(Path(appdata) / "Microsoft/Windows/Start Menu/Programs")
    if programdata:
        roots.append(Path(programdata) / "Microsoft/Windows/Start Menu/Programs")
    if userprofile:
        roots.append(Path(userprofile) / "Desktop")
    if public:
        roots.append(Path(public) / "Desktop")
    roots.append(Path.home() / "Desktop")
    unique = []
    seen = set()
    for root in roots:
        key = str(root).casefold()
        if key not in seen and root.is_dir():
            seen.add(key)
            unique.append(root)
    return unique


def _read_start_menu_apps() -> list[dict]:
    """Получает имена и AUMID приложений Windows без запуска пользовательского кода."""
    command = (
        "Get-StartApps | Select-Object Name,AppID | "
        "ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        apps = []
        for item in data if isinstance(data, list) else []:
            name = str(item.get("Name") or "").strip()
            app_id = str(item.get("AppID") or "").strip()
            if name and app_id:
                apps.append({"name": name, "kind": "aumid", "target": app_id})
        return apps
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return []


def _read_registry_apps() -> list[dict]:
    """Читает только безопасные пути запуска из ключей App Paths и DisplayIcon."""
    try:
        import winreg
    except ImportError:
        return []

    apps = []
    locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    )
    for hive, base in locations:
        try:
            with winreg.OpenKey(hive, base) as root:
                count = winreg.QueryInfoKey(root)[0]
                for index in range(count):
                    try:
                        subkey_name = winreg.EnumKey(root, index)
                        with winreg.OpenKey(root, subkey_name) as key:
                            executable = str(winreg.QueryValueEx(key, "")[0]).strip().strip('"')
                        path = Path(executable)
                        if path.is_file():
                            apps.append({
                                "name": Path(subkey_name).stem,
                                "kind": "executable",
                                "target": str(path),
                            })
                    except (OSError, ValueError):
                        continue
        except OSError:
            continue
    return apps


def _scan_installed_apps() -> list[dict]:
    apps = []
    for root in _shortcut_roots():
        try:
            for shortcut in root.rglob("*"):
                if not shortcut.is_file() or shortcut.suffix.casefold() not in (".lnk", ".url", ".appref-ms"):
                    continue
                name = shortcut.stem.strip()
                if name:
                    apps.append({"name": name, "kind": "shortcut", "target": str(shortcut)})
        except OSError:
            continue

    apps.extend(_read_start_menu_apps())
    apps.extend(_read_registry_apps())

    # Убираем дубликаты одинаковых пунктов и путей.
    unique = {}
    for app in apps:
        key = (app["kind"], str(app["target"]).casefold())
        unique[key] = app
    return list(unique.values())


def _get_installed_apps(force_refresh: bool = False) -> list[dict]:
    global _APP_CACHE, _CACHE_TIME
    now = time.monotonic()
    if force_refresh or not _APP_CACHE or now - _CACHE_TIME > _CACHE_TTL:
        _APP_CACHE = _scan_installed_apps()
        _CACHE_TIME = now
    return list(_APP_CACHE)


def _match_score(query: str, name: str) -> float:
    query_norm = _normalize(query)
    name_norm = _normalize(name)
    if not query_norm or not name_norm:
        return 0.0
    if query_norm == name_norm:
        return 1.0
    if query_norm in name_norm or name_norm in query_norm:
        return 0.94
    query_tokens = set(query_norm.split())
    name_tokens = set(name_norm.split())
    overlap = len(query_tokens & name_tokens) / max(1, len(query_tokens))
    sequence = difflib.SequenceMatcher(None, query_norm, name_norm).ratio()
    return max(sequence, overlap * 0.88)


def _launch_app(app: dict) -> None:
    kind = app["kind"]
    target = app["target"]
    if kind == "aumid":
        subprocess.Popen(
            ["explorer.exe", "shell:AppsFolder\\" + target],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    elif kind == "executable":
        executable = Path(target)
        if not executable.is_file():
            raise FileNotFoundError(f"Файл приложения больше не найден: {target}")
        os.startfile(str(executable))
    else:
        shortcut = Path(target)
        if not shortcut.is_file():
            raise FileNotFoundError(f"Ярлык приложения больше не найден: {target}")
        os.startfile(str(shortcut))


def open_installed_application(app_name: str) -> str:
    """Находит установленное приложение по отображаемому имени и запускает его."""
    query = re.sub(
        r"\b(приложение|программу|программа|мне|пожалуйста|на компьютере|установленное)\b",
        " ",
        str(app_name or ""),
        flags=re.IGNORECASE,
    )
    query = " ".join(query.strip(" .,!?:;«»\"'").split())
    if not query:
        raise ValueError("Не удалось определить название приложения.")

    apps = _get_installed_apps()
    scored = []
    for app in apps:
        score = _match_score(query, app["name"])
        if score >= 0.58:
            scored.append((score, app))
    if not scored:
        # Если приложение только что установили, обновляем список вне интервала кэша.
        apps = _get_installed_apps(force_refresh=True)
        for app in apps:
            score = _match_score(query, app["name"])
            if score >= 0.58:
                scored.append((score, app))

    if not scored:
        raise FileNotFoundError(
            f"Не нашёл установленное приложение «{query}». "
            "Проверьте, есть ли оно в меню «Пуск»."
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_app = scored[0]
    if len(scored) > 1:
        second_score, second_app = scored[1]
        if second_score >= best_score - 0.035 and _normalize(second_app["name"]) != _normalize(best_app["name"]):
            choices = ", ".join(item[1]["name"] for item in scored[:4])
            raise RuntimeError(f"Нашёл несколько похожих приложений: {choices}. Уточните название.")

    _launch_app(best_app)
    print(f"[Приложения] Запускаю «{best_app['name']}».", flush=True)
    return best_app["name"]
