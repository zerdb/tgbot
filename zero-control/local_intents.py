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
# Действия, смысл которых состоит в свободном ответе/анализе ИИ, не превращаем
# в локальные команды: они по определению требуют модель.
_BLOCKED_ACTIONS = {"ai_chat", "camera_question", "inspect_camera_image", "unknown"}


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
    if not action or action in _BLOCKED_ACTIONS:
        raise ValueError("Это намерение нельзя превратить в локальное действие.")
    if not isinstance(parameters, dict):
        raise ValueError("Параметры должны быть JSON-объектом.")
    clean_params = {
        key: value for key, value in parameters.items()
        if key in _ALLOWED_PARAMETERS and isinstance(value, (str, bool))
    }
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
            if action in _BLOCKED_ACTIONS:
                return None
            return {
                "schema_version": 1,
                "kind": "execute",
                "action": action,
                "goal": "Пользовательское локальное правило",
                "target": {},
                "source": {"type": "spoken_text", "name": ""},
                "method": "Точное совпадение с подтверждённым пользователем правилом",
                "parameters": {
                    key: value for key, value in (rule.get("parameters") or {}).items()
                    if key in _ALLOWED_PARAMETERS and isinstance(value, (str, bool))
                },
                "confidence": 1.0,
                "clarification": "",
                "response": "",
            }
    return None
