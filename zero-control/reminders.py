"""Unified notes, tasks and reminders with one persistent item model."""
from __future__ import annotations
import json, os, queue, re, threading
from datetime import datetime, timedelta
from pathlib import Path
from notifications import show_notification, speak_text
from agent_core import APP_DATA

_APP_DATA = APP_DATA
_ITEMS_PATH = _APP_DATA / "notes_and_tasks.json"
_LEGACY_REMINDERS_PATH = _APP_DATA / "reminders.json"
_LEGACY_NOTES_PATH = Path(__file__).resolve().parent / "Заметки" / "Мои заметки.txt"
_LEGACY_MEMORY_PATH = _APP_DATA / "assistant_memory.json"
_lock = threading.RLock()
_items: list[dict] = []
_loaded = False
_due_items: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()
_reminder_thread_started = False
_reminder_stop_event = threading.Event()
_reminder_thread: threading.Thread | None = None

def normalize_command(text: str) -> str:
    value = str(text or "").lower().replace("ё", "е")
    value = re.sub(r"[^а-яa-z0-9.:/ -]+", " ", value)
    return " ".join(value.split()).strip(" .,:;!?")

def parse_reminder(text: str):
    source = normalize_command(text)
    if not source.startswith("напомни "):
        if source.startswith("через ") and " напомни " in source:
            source = "напомни " + source
        else:
            return None
    body = re.sub(r"^мне\s+", "", source[len("напомни "):].strip())
    now, due, rest = datetime.now(), None, body
    if rest.startswith("через "):
        m = re.match(r"через\s+полчаса(?:\s+|$)(.*)", rest)
        if m:
            due, rest = now + timedelta(minutes=30), m.group(1).strip()
        else:
            m = re.match(r"через\s+(?:(\d+)\s*(?:час|часа|часов|ч)\s*)?(?:(\d+)\s*(?:минуту|минуты|минут|минута|мин)\s*)?(?:(\d+)\s*(?:секунду|секунды|секунд|сек)\s*)?(.*)", rest)
            if m:
                hours, minutes, seconds = (int(m.group(i) or 0) for i in (1,2,3))
                remainder = m.group(4).strip()
                if not any(m.group(i) for i in (1,2,3)):
                    unit = re.match(r"через\s+(час|часа|часов|ч|минуту|минута|минуты|минут|мин|секунду|секунда|секунды|секунд|сек)\b", rest)
                    if unit:
                        token = unit.group(1)
                        if token in {"час","часа","часов","ч"}: hours = 1
                        elif token in {"минуту","минута","минуты","минут","мин"}: minutes = 1
                        else: seconds = 1
                        remainder = rest[unit.end():].strip()
                if hours or minutes or seconds:
                    due = now + timedelta(hours=hours, minutes=minutes, seconds=seconds)
                    rest = re.sub(r"^напомни(?:\s+мне)?\s+", "", remainder)
    if due is None:
        absolute = re.match(r"^(\d{2}\.\d{2}\.\d{4})\s+(\d{1,2}):(\d{2})\s+(.*)$", rest)
        if absolute:
            try:
                due = datetime.strptime(absolute.group(1) + " " + absolute.group(2) + ":" + absolute.group(3), "%d.%m.%Y %H:%M")
                rest = absolute.group(4).strip()
            except ValueError:
                return None
    if due is None and rest.startswith("завтра"):
        tomorrow = now.date() + timedelta(days=1)
        m = re.match(r"завтра\s+в\s+(\d{1,2})(?::(\d{2}))?\s*(утра|вечера|дня)?\s*(.*)", rest)
        if m:
            hour, minute, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
            if period == "вечера" and hour < 12: hour += 12
            elif period == "утра" and hour == 12: hour = 0
            if hour > 23 or minute > 59: return None
            due = datetime.combine(tomorrow, datetime.min.time()).replace(hour=hour, minute=minute)
            rest = m.group(4).strip()
        else:
            m = re.match(r"завтра\s+(утром|днем|днём|вечером|ночью)\s*(.*)", rest)
            if m:
                hour = {"утром":9,"днем":13,"днём":13,"вечером":18,"ночью":22}[m.group(1)]
                due = datetime.combine(tomorrow, datetime.min.time()).replace(hour=hour)
                rest = m.group(2).strip()
    if due is None or due <= now or not rest: return None
    return due, rest

def _new_item(text: str, due: datetime | None = None) -> dict:
    now = datetime.now()
    return {"id": now.strftime("%Y%m%d%H%M%S%f"), "text": str(text).strip()[:2000],
            "created_at": now.isoformat(timespec="seconds"),
            "due_at": due.isoformat(timespec="seconds") if due else None,
            "completed": False, "notified": False}

def _save_locked():
    _APP_DATA.mkdir(parents=True, exist_ok=True)
    temp = _ITEMS_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(_items, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(_ITEMS_PATH)

def _migrate_legacy_locked():
    migrated = []
    try:
        old = json.loads(_LEGACY_REMINDERS_PATH.read_text(encoding="utf-8"))
        for entry in old if isinstance(old, list) else []:
            try:
                due, message = datetime.fromisoformat(entry["when"]), str(entry["message"]).strip()
                if message: migrated.append(_new_item(message, due))
            except (KeyError, TypeError, ValueError): continue
    except (OSError, json.JSONDecodeError): pass
    try:
        legacy_memory = json.loads(_LEGACY_MEMORY_PATH.read_text(encoding="utf-8"))
        for note in legacy_memory.get("notes", []) if isinstance(legacy_memory, dict) else []:
            note_text = str(note or "").strip()
            if note_text:
                migrated.append(_new_item(note_text))
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    try:
        content = _LEGACY_NOTES_PATH.read_text(encoding="utf-8")
        for block in re.split(r"\n\s*={8,}\s*\n", content):
            block = block.strip()
            if not block: continue
            m = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*\n?(.*)", block, re.S)
            if m:
                stamp, body = m.groups()
                item = _new_item(body.strip())
                try: item["created_at"] = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").isoformat(timespec="seconds")
                except ValueError: pass
                if item["text"]: migrated.append(item)
            else: migrated.append(_new_item(block))
    except OSError: pass
    return migrated

def _load_locked():
    global _loaded
    if _loaded: return
    _loaded = True
    try:
        raw = json.loads(_ITEMS_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("id") and str(item.get("text","")).strip():
                    _items.append({"id":str(item["id"]), "text":str(item["text"])[:2000],
                        "created_at":str(item.get("created_at") or datetime.now().isoformat(timespec="seconds")),
                        "due_at":item.get("due_at"), "completed":bool(item.get("completed",False)),
                        "notified":bool(item.get("notified",False))})
    except (OSError, json.JSONDecodeError):
        _items.extend(_migrate_legacy_locked())
        if _items: _save_locked()

def add_note(text: str) -> bool:
    text = str(text or "").strip()
    if not text: print("Пустую заметку нельзя сохранить."); return False
    with _lock:
        _load_locked(); _items.append(_new_item(text)); _save_locked()
    print("Запись сохранена в общих заметках и делах.")
    try: speak_text("Запись сохранена.")
    except Exception as exc: print(f"Не удалось озвучить сохранение: {exc}")
    return True

def add_reminder(text: str) -> bool:
    parsed = parse_reminder(text)
    if not parsed:
        print("Не удалось разобрать время. Примеры: «напомни через 10 минут проверить почту», «напомни завтра в 9 позвонить».")
        return False
    due, message = parsed
    with _lock: _load_locked(); _items.append(_new_item(message,due)); _save_locked()
    print(f"Напоминание добавлено в общие записи на {due:%d.%m.%Y %H:%M}: {message}")
    return True

def list_items(include_completed: bool = True) -> list[dict]:
    with _lock:
        _load_locked()
        values = [dict(x) for x in _items if include_completed or not x["completed"]]
    return sorted(values, key=lambda x:(x["completed"], x["due_at"] or "9999", x["created_at"]))

def update_item(item_id: str, text: str, due_text: str = "") -> bool:
    text = str(text or "").strip()
    if not text: return False
    due = None
    if due_text.strip():
        try:
            due = datetime.strptime(due_text.strip(), "%d.%m.%Y %H:%M")
            if due <= datetime.now(): return False
        except ValueError:
            parsed = parse_reminder("напомни " + due_text.strip() + " " + text)
            if not parsed: return False
            due = parsed[0]
    with _lock:
        _load_locked()
        for item in _items:
            if item["id"] == str(item_id):
                item.update(text=text[:2000], due_at=due.isoformat(timespec="seconds") if due else None, notified=False)
                _save_locked(); return True
    return False

def complete_item(item_id: str) -> bool:
    with _lock:
        _load_locked()
        for item in _items:
            if item["id"] == str(item_id):
                item["completed"] = True; _save_locked(); return True
    return False

def complete_item_by_text(query: str) -> bool:
    query = normalize_command(query)
    if not query: return False
    with _lock:
        _load_locked()
        candidates = [x for x in _items if not x["completed"]]
        match = next((x for x in candidates if query in normalize_command(x["text"])), None)
        if match is None and len(candidates) == 1: match = candidates[0]
        if match is None: return False
        match["completed"] = True; _save_locked()
    print(f"Выполнено: {match['text']}")
    try: speak_text("Отмечено выполненным.")
    except Exception: pass
    return True

def delete_item(item_id: str) -> bool:
    with _lock:
        _load_locked(); count = len(_items)
        _items[:] = [x for x in _items if x["id"] != str(item_id)]
        if len(_items) == count: return False
        _save_locked(); return True

def list_reminders():
    result = []
    for item in list_items(False):
        if item.get("due_at"):
            try: result.append((datetime.fromisoformat(item["due_at"]),item["text"]))
            except ValueError: pass
    return sorted(result,key=lambda x:x[0])

def delete_reminder(index: int):
    scheduled = list_reminders()
    if index < 0 or index >= len(scheduled): return False
    when, text = scheduled[index]
    for item in list_items(False):
        if item["text"] == text and item.get("due_at") == when.isoformat(timespec="seconds"):
            return delete_item(item["id"])
    return False

def reminder_worker():
    while not _reminder_stop_event.is_set():
        now = datetime.now()
        with _lock:
            _load_locked(); changed = False
            for item in _items:
                if item["completed"] or item["notified"] or not item.get("due_at"): continue
                try: due = datetime.fromisoformat(item["due_at"])
                except (TypeError,ValueError): continue
                if due <= now:
                    item["notified"] = True; _due_items.put((item["id"],item["text"])); changed = True
            if changed:
                try: _save_locked()
                except OSError as exc: print(f"Не удалось обновить записи: {exc}")
        _reminder_stop_event.wait(1)

def deliver_due_reminders():
    while True:
        try: _item_id, message = _due_items.get_nowait()
        except queue.Empty: break
        print(f"НАПОМИНАНИЕ: {message}")
        try: show_notification("Напоминание",message)
        except Exception as exc: print(f"Не удалось показать уведомление: {exc}")
        try: speak_text("Напоминание. " + message)
        except Exception as exc: print(f"Не удалось озвучить напоминание: {exc}")

def start_reminder_service():
    global _reminder_thread_started, _reminder_thread
    if not _reminder_thread_started:
        _reminder_stop_event.clear()
        _reminder_thread = threading.Thread(target=reminder_worker,daemon=False,name="notes-reminders-service")
        _reminder_thread.start(); _reminder_thread_started = True

def stop_reminder_service(timeout: float = 3.0):
    global _reminder_thread_started, _reminder_thread
    _reminder_stop_event.set(); thread = _reminder_thread
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=max(0.0,timeout))
    if thread is None or not thread.is_alive():
        _reminder_thread = None; _reminder_thread_started = False
