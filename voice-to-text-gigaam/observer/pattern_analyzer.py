"""Explainable local pattern detection over Observer metadata."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib


def analyze_patterns(store, days: int = 7, minimum: int = 3) -> list[dict]:
    """Create conservative suggestions from repeated metadata patterns only."""
    days = max(1, min(int(days), 30))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    events = store.list_events(limit=1000)
    events = [e for e in events if e.get("occurred_at", "") >= cutoff]
    suggestions = []

    app_counts = Counter(
        (e.get("object_name") or "Неизвестная программа")
        for e in events if e.get("category") == "apps" and e.get("event_type") == "started"
    )
    for app, count in app_counts.most_common(10):
        if count >= minimum:
            suggestions.append(_suggest(
                "repeated-app:" + app.casefold(),
                f"Часто запускается: {app}",
                f"За последние {days} дн. зафиксировано {count} запусков. "
                "Можно подумать о более быстром доступе или объединении повторяющихся действий.",
                count,
            ))

    folder_counts = Counter()
    for event in events:
        if event.get("category") != "files":
            continue
        path = event.get("object_path") or ""
        parent = path.rsplit("/", 1)[0].rsplit("\\", 1)[0] if path else ""
        if parent:
            folder_counts[parent] += 1
    for folder, count in folder_counts.most_common(8):
        if count >= minimum:
            suggestions.append(_suggest(
                "busy-folder:" + folder.casefold(),
                "Активная папка",
                f"В папке «{folder}» за последние {days} дн. замечено {count} изменений файлов. "
                "Возможно, стоит добавить её в быстрый доступ или настроить отдельный рабочий процесс.",
                count,
            ))

    daily = defaultdict(set)
    for event in events:
        if event.get("category") == "apps" and event.get("event_type") == "started":
            try:
                day = datetime.fromisoformat(event["occurred_at"]).astimezone().date().isoformat()
            except (ValueError, TypeError):
                continue
            daily[day].add(event.get("object_name") or "")
    recurring = Counter(app for apps in daily.values() for app in apps if app)
    for app, days_seen in recurring.most_common(8):
        if days_seen >= min(3, days):
            suggestions.append(_suggest(
                "daily-app:" + app.casefold(),
                f"Регулярная программа: {app}",
                f"Программа встречалась в журнале в {days_seen} разных днях. "
                "Если это часть ежедневного старта, можно добавить её в будущий утренний сценарий.",
                days_seen,
            ))

    # Detect recurring ordered sequences of foreground applications.
    focus_events = sorted(
        (e for e in events if e.get("category") == "focus"
         and e.get("event_type") == "focus_session" and e.get("object_name")),
        key=lambda item: item.get("occurred_at", ""),
    )
    sessions = []
    for event in focus_events:
        app = str(event.get("object_name")).strip()
        if not app:
            continue
        if not sessions or sessions[-1] != app:
            sessions.append(app)
    sequence_counts = Counter(
        tuple(sessions[index:index + 3])
        for index in range(max(0, len(sessions) - 2))
    )
    for sequence, count in sequence_counts.most_common(5):
        if count >= 2 and len(set(sequence)) == 3:
            readable = " → ".join(sequence)
            suggestions.append(_suggest(
                "work-sequence:" + "|".join(item.casefold() for item in sequence),
                f"Повторяющийся сценарий: {readable}",
                f"Одинаковая последовательность из трёх приложений встретилась {count} раза. "
                "Можно превратить её в быстрый рабочий сценарий.",
                count,
            ))

    return suggestions


def _suggest(key: str, title: str, description: str, evidence_count: int) -> dict:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return {
        "pattern_key": digest,
        "title": title,
        "description": description,
        "evidence_count": int(evidence_count),
    }
