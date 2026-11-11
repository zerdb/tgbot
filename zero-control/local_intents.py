"""Локальный журнал распознанных ИИ намерений и проверенные пользовательские правила."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from agent_core import APP_DATA

HISTORY_PATH = APP_DATA / "recognized_intents.json"
RULES_PATH = APP_DATA / "local_intents.json"
_LOCK = RLock()
_ALLOWED_PARAMETERS = {
    "attach_copied_files", "recipient_name", "reminder_text", "note_text",
    "item_text", "query", "question", "app", "app_name", "folder",
    "export_format",
}
# Параметры проверяются не только по общему allowlist, но и по конкретному действию.
# Это не позволяет сохранить, например, app_name для open_application вместо app.
_ACTION_PARAMETER_TYPES = {
    "add_contact": {},
    "open_contacts": {},
    "open_assistant_settings": {},
    "read_unread_mail": {},
    "email_compose": {"recipient_name": str, "attach_copied_files": bool},
    "save_note": {},
    "add_note": {"note_text": str},
    "complete_item": {"item_text": str},
    "clipboard_to_excel": {},
    "lock_computer": {},
    "reboot_computer": {},
    "open_downloads": {},
    "open_recycle_bin": {},
    "open_application": {"app": str},
    "open_installed_application": {"app_name": str},
    "open_settings": {},
    "open_magnifier": {},
    "open_onscreen_keyboard": {},
    "empty_recycle_bin": {},
    "screenshot": {},
    "inspect_screen": {},
    "paste_clipboard_to_application": {"app_name": str},
    "reminder": {"reminder_text": str},
    "organize_folder": {},
    "open_reminders": {},
    "open_mail_client": {},
    "search_web": {"query": str},
    "search_files": {"query": str, "export_format": str},
    "open_folder": {"folder": str},
}
_REQUIRED_ACTION_PARAMETERS = {
    "add_note": {"note_text"},
    "complete_item": {"item_text"},
    "open_application": {"app"},
    "open_installed_application": {"app_name"},
    "paste_clipboard_to_application": {"app_name"},
    "reminder": {"reminder_text"},
    "search_web": {"query"},
    "search_files": {"query"},
    "open_folder": {"folder"},
}
_PARAMETER_CHOICES = {
    "app": {"notepad", "calculator", "browser", "word", "excel", "images"},
    "export_format": {"excel", "word", "text"},
}


def _validate_action_parameters(action: str, parameters: dict) -> dict:
    """Проверяет имена, типы, обязательность и допустимые значения параметров действия."""
    schema = _ACTION_PARAMETER_TYPES.get(action)
    if schema is None:
        raise ValueError("Неизвестное локальное действие: " + str(action))
    if not isinstance(parameters, dict):
        raise ValueError("Параметры должны быть JSON-объектом.")

    invalid = [key for key in parameters if key not in schema]
    if invalid:
        raise ValueError(
            "Параметры не подходят для действия %s: %s"
            % (action, ", ".join(map(str, invalid)))
        )

    clean = {}
    for key, value in parameters.items():
        expected_type = schema[key]
        if type(value) is not expected_type:
            raise ValueError(
                "Параметр %s для действия %s должен иметь тип %s."
                % (key, action, "boolean" if expected_type is bool else "string")
            )
        choices = _PARAMETER_CHOICES.get(key)
        if choices is not None and value not in choices:
            raise ValueError(
                "Недопустимое значение параметра %s: %s." % (key, value)
            )
        clean[key] = value

    missing = _REQUIRED_ACTION_PARAMETERS.get(action, set()) - clean.keys()
    if missing:
        raise ValueError(
            "Для действия %s обязательны параметры: %s"
            % (action, ", ".join(sorted(missing)))
        )
    return clean


# Действия, смысл которых состоит в свободном ответе/анализе ИИ, не превращаем
# в локальные команды: они по определению требуют модель.
_BLOCKED_ACTIONS = {"ai_chat", "camera_question", "inspect_camera_image", "unknown"}
_ALLOWED_ACTIONS = {
    "add_contact", "open_contacts", "open_assistant_settings", "read_unread_mail",
    "email_compose", "save_note", "add_note", "complete_item", "clipboard_to_excel",
    "lock_computer", "reboot_computer", "open_downloads", "open_recycle_bin",
    "open_application", "open_installed_application", "open_settings",
    "open_magnifier", "open_onscreen_keyboard",
    "empty_recycle_bin", "screenshot", "inspect_screen", "paste_clipboard_to_application",
    "reminder", "organize_folder", "open_reminders", "open_mail_client",
    "search_web", "search_files", "open_folder",
}


def normalize_phrase(value: str) -> str:
    value = str(value or "").lower().replace("ё", "е")
    return re.sub(r"\s+", " ", value).strip(" .,!?:;\t\r\n")


def _read(path: Path, fallback):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(fallback)) else fallback
    except (OSError, json.JSONDecodeError):
        return fallback


def _write(path: Path, value) -> None:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _safe_intent(intent: dict) -> dict:
    params = intent.get("parameters") if isinstance(intent.get("parameters"), dict) else {}
    return {
        "schema_version": 1,
        "kind": str(intent.get("kind") or "clarify"),
        "action": str(intent.get("action") or "unknown"),
        "goal": str(intent.get("goal") or ""),
        "target": intent.get("target") if isinstance(intent.get("target"), dict) else {},
        "source": intent.get("source") if isinstance(intent.get("source"), dict) else {},
        "method": str(intent.get("method") or ""),
        "parameters": {
            key: value for key, value in params.items()
            if key in _ALLOWED_PARAMETERS and isinstance(value, (str, bool))
        },
        "confidence": max(0.0, min(1.0, float(intent.get("confidence") or 0.0))),
        "clarification": str(intent.get("clarification") or ""),
        "response": str(intent.get("response") or ""),
    }


def record_intent(phrase: str, intent: dict, provider: str = "groq") -> None:
    """Сохраняет локально результат семантической классификации; ошибки не ломают команду."""
    phrase = str(phrase or "").strip()
    if not phrase or not isinstance(intent, dict):
        return
    try:
        safe = _safe_intent(intent)
        record = {
            "id": uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "provider": str(provider or "ai"),
            "phrase": phrase[:4000],
            "intent": safe,
            "promoted": False,
        }
        with _LOCK:
            records = _read(HISTORY_PATH, [])
            records.append(record)
            _write(HISTORY_PATH, records[-500:])
    except Exception as exc:
        print(f"[Намерения] Не удалось сохранить запись журнала: {exc}", flush=True)


def list_records() -> list[dict]:
    with _LOCK:
        return list(reversed(_read(HISTORY_PATH, [])))


def delete_record(record_id: str) -> bool:
    with _LOCK:
        records = _read(HISTORY_PATH, [])
        updated = [item for item in records if item.get("id") != record_id]
        if len(updated) == len(records):
            return False
        _write(HISTORY_PATH, updated)
        return True


def promote_record(record_id: str, phrase: str, action: str, parameters: dict) -> None:
    """Публикует только проверенное действие как exact-match правило, без regex/кода."""
    phrase = str(phrase or "").strip()
    normalized = normalize_phrase(phrase)
    action = str(action or "").strip()
    if not normalized:
        raise ValueError("Фраза для локального правила не может быть пустой.")
    if action not in _ALLOWED_ACTIONS or action in _BLOCKED_ACTIONS:
        raise ValueError("Это намерение нельзя превратить в локальное действие.")
    if not isinstance(parameters, dict):
        raise ValueError("Параметры должны быть JSON-объектом.")
    clean_params = _validate_action_parameters(action, parameters)
    with _LOCK:
        rules = _read(RULES_PATH, {"schema_version": 1, "rules": []})
        if not isinstance(rules, dict) or not isinstance(rules.get("rules"), list):
            rules = {"schema_version": 1, "rules": []}
        rules["rules"] = [item for item in rules["rules"] if normalize_phrase(item.get("phrase")) != normalized]
        rules["rules"].append({
            "phrase": phrase,
            "normalized": normalized,
            "action": action,
            "parameters": clean_params,
            "source_record_id": record_id,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        _write(RULES_PATH, rules)
        records = _read(HISTORY_PATH, [])
        for item in records:
            if item.get("id") == record_id:
                item["promoted"] = True
                item["promoted_phrase"] = phrase
                break
        _write(HISTORY_PATH, records)


def match_local_intent(phrase: str):
    normalized = normalize_phrase(phrase)
    if not normalized:
        return None
    with _LOCK:
        rules = _read(RULES_PATH, {"schema_version": 1, "rules": []})
    for rule in reversed(rules.get("rules", [])):
        if rule.get("normalized") == normalized:
            action = str(rule.get("action") or "unknown")
            if action not in _ALLOWED_ACTIONS or action in _BLOCKED_ACTIONS:
                return None
            try:
                clean_parameters = _validate_action_parameters(
                    action, rule.get("parameters") or {}
                )
            except ValueError as exc:
                print("[Намерения] Пропускаю несовместимое локальное правило: %s" % exc, flush=True)
                continue
            return {
                "schema_version": 1,
                "kind": "execute",
                "action": action,
                "goal": "Пользовательское локальное правило",
                "target": {},
                "source": {"type": "spoken_text", "name": ""},
                "method": "Точное совпадение с подтверждённым пользователем правилом",
                "parameters": clean_parameters,
                "confidence": 1.0,
                "clarification": "",
                "response": "",
            }
    return None
