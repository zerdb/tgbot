"""Reminder parsing, storage and background worker."""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta
from notifications import show_notification, speak_text

_reminder_lock = threading.Lock()
_reminders: list[tuple[datetime, str]] = []
_reminder_thread_started = False

def normalize_command(text: str) -> str:
    normalized = text.lower().replace("ё", "е")
    normalized = re.sub(r"[^а-яa-z0-9.:/ -]+", " ", normalized)
    return " ".join(normalized.split()).strip(" .,:;!?")


def reminder_worker():
    while True:
        due = []
        now = datetime.now()
        with _reminder_lock:
            remaining = []
            for when, message in _reminders:
                if when <= now:
                    due.append((when, message))
                else:
                    remaining.append((when, message))
            _reminders[:] = remaining
        for when, message in due:
            print(f"НАПОМИНАНИЕ: {message}")
            try:
                show_notification("Напоминание", message)
            except Exception as exc:
                print(f"Не удалось показать уведомление: {exc}")
            speak_text("Напоминание. " + message)
        time.sleep(1)

def start_reminder_service():
    global _reminder_thread_started
    if not _reminder_thread_started:
        threading.Thread(target=reminder_worker, daemon=True, name="reminder-service").start()
        _reminder_thread_started = True

def parse_reminder(text: str):
    source = normalize_command(text)
    if not source.startswith("напомни "):
        return None
    body = source[len("напомни "):].strip()
    # В разговорной речи часто говорят «напомни мне ...».
    body = re.sub(r"^мне\s+", "", body)
    now = datetime.now()
    due = None
    rest = body

    # Относительное время: «через минуту», «через час», «через 1 час 20 минут».
    if rest.startswith("через "):
        m = re.match(r"через\s+полчаса(?:\s+|$)(.*)", rest)
        if m:
            due, rest = now + timedelta(minutes=30), m.group(1).strip()
        else:
            m = re.match(
                r"через\s+"
                r"(?:(\d+)\s*(?:час|часа|часов|ч)\s*)?"
                r"(?:(\d+)\s*(?:минуту|минуты|минут|минута|мин)\s*)?"
                r"(?:(\d+)\s*(?:секунду|секунды|секунд|сек)\s*)?"
                r"(.*)",
                rest,
            )
            if m:
                hours, minutes, seconds = (int(m.group(i) or 0) for i in (1, 2, 3))
                remainder = m.group(4).strip()
                # Если единица времени названа без числа, подразумевается одна.
                if not any(m.group(i) for i in (1, 2, 3)):
                    unit = re.match(r"через\s+(час|часа|часов|ч|минуту|минута|минуты|минут|мин|секунду|секунда|секунды|секунд|сек)\b", rest)
                    if unit:
                        token = unit.group(1)
                        if token in {"час", "часа", "часов", "ч"}:
                            hours = 1
                        elif token in {"минуту", "минута", "минуты", "минут", "мин"}:
                            minutes = 1
                        else:
                            seconds = 1
                        remainder = rest[unit.end():].strip()
                if hours or minutes or seconds:
                    due = now + timedelta(hours=hours, minutes=minutes, seconds=seconds)
                    rest = remainder
    # "завтра в 9 утра", "завтра утром", "завтра в 09:30".
    if due is None and rest.startswith("завтра"):
        tomorrow = now.date() + timedelta(days=1)
        m = re.match(r"завтра\s+в\s+(\d{1,2})(?::(\d{2}))?\s*(утра|вечера|дня)?\s*(.*)", rest)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            period = m.group(3)
            if period == "вечера" and hour < 12:
                hour += 12
            elif period in ("утра", "дня") and hour == 12:
                hour = 0 if period == "утра" else 12
            if hour > 23 or minute > 59:
                return None
            due = datetime.combine(tomorrow, datetime.min.time()).replace(hour=hour, minute=minute)
            rest = m.group(4).strip()
        else:
            m = re.match(r"завтра\s+(утром|днем|днём|вечером|ночью)\s*(.*)", rest)
            if m:
                hour = {"утром": 9, "днем": 13, "днём": 13, "вечером": 18, "ночью": 22}[m.group(1)]
                due = datetime.combine(tomorrow, datetime.min.time()).replace(hour=hour)
                rest = m.group(2).strip()
    if due is None or due <= now or not rest:
        return None
    return due, rest

def add_reminder(text: str):
    parsed = parse_reminder(text)
    if not parsed:
        print("Не удалось разобрать напоминание. Примеры: «напомни через полчаса проверить почту», "
              "«напомни через 1 час 20 минут позвонить», «напомни завтра в 9 утра о встрече».")
        return
    due, message = parsed
    with _reminder_lock:
        _reminders.append((due, message))
    print(f"Напоминание установлено на {due:%d.%m.%Y %H:%M}: {message}")

