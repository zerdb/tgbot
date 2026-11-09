"""Shared configuration and explicit user-approved AI memory for Zero Control."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from threading import RLock

APP_DATA = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "ZeroControl"
LEGACY_APP_DATA = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "GigaAMVoiceAssistant"


def _migrate_legacy_app_data() -> None:
    """Copy legacy user data to the new app folder without deleting originals."""
    if not LEGACY_APP_DATA.is_dir():
        return
    try:
        APP_DATA.mkdir(parents=True, exist_ok=True)
        for source in LEGACY_APP_DATA.iterdir():
            target = APP_DATA / source.name
            if target.exists():
                continue
            if source.is_file():
                shutil.copy2(source, target)
            elif source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
    except OSError as exc:
        print(f"Не удалось перенести старые данные Zero Control: {exc}")


_migrate_legacy_app_data()
CONFIG_PATH = APP_DATA / "settings.json"
MEMORY_PATH = APP_DATA / "assistant_memory.json"
_LOCK = RLock()
DEFAULTS = {
    "groq_model": "openai/gpt-oss-20b",
    "mail_login": "zerdb@mail.ru",
    "imap_host": "imap.mail.ru",
    "imap_port": 993,
    "remember_chat_history": True,
    "clean_dictation_with_ai": False,
    "mft_refresh_interval_days": 7,
    "mft_last_refresh_at": 0,
    "mft_last_reminder_at": 0,
}


def _read_json(path: Path, fallback):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(fallback)) else fallback
    except (OSError, json.JSONDecodeError):
        return fallback


def load_settings() -> dict:
    with _LOCK:
        stored = _read_json(CONFIG_PATH, {})
        # Remove obsolete API provider settings from older configurations.
        stored.pop("openrouter_base_url", None)
        stored.pop("openrouter_model", None)
        stored.pop("ollama_model", None)
        # Migrate the retired Groq model from existing local settings.
        if stored.get("groq_model") in ("llama-3.3-70b-versatile", "openai/gpt-oss-120b"):
            stored["groq_model"] = DEFAULTS["groq_model"]
        return {**DEFAULTS, **stored}


def save_settings(values: dict) -> dict:
    allowed = set(DEFAULTS)
    clean = {}
    for key, value in values.items():
        if key not in allowed:
            continue
        if key == "imap_port":
            try:
                value = max(1, min(65535, int(value)))
            except (TypeError, ValueError):
                continue
        elif key in ("remember_chat_history", "clean_dictation_with_ai"):
            value = bool(value)
        elif key == "mft_refresh_interval_days":
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
            if value not in (3, 7, 14, 30):
                continue
        elif key in ("mft_last_refresh_at", "mft_last_reminder_at"):
            try:
                value = max(0, int(value))
            except (TypeError, ValueError):
                continue
        else:
            value = str(value).strip()
        clean[key] = value
    with _LOCK:
        current = load_settings()
        current.update(clean)
        APP_DATA.mkdir(parents=True, exist_ok=True)
        temp = CONFIG_PATH.with_suffix(".tmp")
        temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(CONFIG_PATH)
        return current


def get_secret_env(name: str) -> str:
    return os.getenv(name, "").strip()


def get_mail_password() -> str:
    """Read the mail app password from Windows Credential Manager."""
    try:
        import keyring
        return keyring.get_password("ZeroControl", "mail_password") or keyring.get_password("GigaAMVoiceAssistant", "mail_password") or ""
    except Exception as exc:
        print(f"Не удалось прочитать пароль почты: {exc}")
        return ""


def set_mail_password(password: str) -> None:
    """Store the mail app password in Windows Credential Manager."""
    password = str(password or "")
    if not password:
        raise ValueError("Пароль почты не может быть пустым.")
    import keyring
    keyring.set_password("ZeroControl", "mail_password", password)


def get_groq_api_key() -> str:
    """Read Groq API key from Windows Credential Manager."""
    try:
        import keyring
        return keyring.get_password("ZeroControl", "groq_api_key") or keyring.get_password("GigaAMVoiceAssistant", "groq_api_key") or ""
    except Exception as exc:
        print(f"Не удалось прочитать ключ Groq: {exc}")
        return ""


def set_groq_api_key(api_key: str) -> None:
    api_key = str(api_key or "").strip()
    if not api_key:
        raise ValueError("Ключ Groq не может быть пустым.")
    import keyring
    keyring.set_password("ZeroControl", "groq_api_key", api_key)


def delete_groq_api_key() -> None:
    import keyring
    try:
        keyring.delete_password("ZeroControl", "groq_api_key")
        try:
            keyring.delete_password("GigaAMVoiceAssistant", "groq_api_key")
        except keyring.errors.PasswordDeleteError:
            pass
    except keyring.errors.PasswordDeleteError:
        pass



def get_camera_password() -> str:
    """Read the shared camera password from Windows Credential Manager."""
    try:
        import keyring
        return keyring.get_password("ZeroControl", "camera") or keyring.get_password("GigaAMVoiceAssistant", "camera") or ""
    except Exception as exc:
        print(f"Не удалось прочитать пароль камеры: {exc}")
        return ""


def set_camera_password(password: str) -> None:
    """Store the camera password in the OS credential vault."""
    password = str(password or "")
    if not password:
        raise ValueError("Пароль камеры не может быть пустым.")
    import keyring
    keyring.set_password("ZeroControl", "camera", password)


def delete_camera_password() -> None:
    import keyring
    try:
        keyring.delete_password("ZeroControl", "camera")
        try:
            keyring.delete_password("GigaAMVoiceAssistant", "camera")
        except keyring.errors.PasswordDeleteError:
            pass
    except keyring.errors.PasswordDeleteError:
        pass


def get_moondream_api_key() -> str:
    """Read Moondream API key from Windows Credential Manager."""
    try:
        import keyring
        return keyring.get_password("ZeroControl", "moondream_api_key") or keyring.get_password("GigaAMVoiceAssistant", "moondream_api_key") or ""
    except Exception as exc:
        print(f"Не удалось прочитать ключ Moondream: {exc}")
        return ""


def set_moondream_api_key(api_key: str) -> None:
    api_key = str(api_key or "").strip()
    if not api_key:
        raise ValueError("Ключ Moondream не может быть пустым.")
    import keyring
    keyring.set_password("ZeroControl", "moondream_api_key", api_key)


def delete_moondream_api_key() -> None:
    import keyring
    try:
        keyring.delete_password("ZeroControl", "moondream_api_key")
        try:
            keyring.delete_password("GigaAMVoiceAssistant", "moondream_api_key")
        except keyring.errors.PasswordDeleteError:
            pass
    except keyring.errors.PasswordDeleteError:
        pass


def load_memory() -> dict:
    with _LOCK:
        return _read_json(MEMORY_PATH, {"notes": [], "history": []})


def remember_note(note: str) -> None:
    note = str(note or "").strip()
    if not note:
        raise ValueError("Пустую заметку нельзя сохранить в память.")
    with _LOCK:
        data = load_memory()
        data.setdefault("notes", []).append(note[:1000])
        data["notes"] = data["notes"][-100:]
        _write_memory(data)


def forget_notes() -> None:
    with _LOCK:
        data = load_memory()
        data["notes"] = []
        _write_memory(data)


def clear_chat_history() -> None:
    with _LOCK:
        data = load_memory()
        data["history"] = []
        _write_memory(data)


def get_ai_context() -> list[dict]:
    settings = load_settings()
    if not settings.get("remember_chat_history", True):
        return []
    data = load_memory()
    messages = []
    notes = data.get("notes", [])[-20:]
    if notes:
        messages.append({"role": "system", "content": "Пользователь явно сохранил эти заметки в память помощника. Используй их только когда уместно:\n- " + "\n- ".join(str(x) for x in notes)})
    history = data.get("history", [])
    for item in history[-12:]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant") and item.get("content"):
            messages.append({"role": item["role"], "content": str(item["content"])[:4000]})
    return messages


def save_ai_exchange(question: str, answer: str) -> None:
    if not load_settings().get("remember_chat_history", True):
        return
    with _LOCK:
        data = load_memory()
        history = data.setdefault("history", [])
        history.extend([
            {"role": "user", "content": str(question)[:4000]},
            {"role": "assistant", "content": str(answer)[:4000]},
        ])
        data["history"] = history[-24:]
        _write_memory(data)


def _write_memory(data: dict) -> None:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    temp = MEMORY_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(MEMORY_PATH)
