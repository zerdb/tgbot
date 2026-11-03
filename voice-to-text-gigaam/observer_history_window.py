"""Local event history and notes UI for GigaAM Observer."""
from __future__ import annotations

import csv
import json
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk


CATEGORY_LABELS = {
    "files": "Файлы",
    "apps": "Программы",
    "focus": "Активные окна",
    "clipboard": "Буфер обмена",
    "voice": "Заметки",
    "printing": "Печать",
    "usb": "USB",
    "browser": "Браузер",
}


def _format_duration(value):
    try:
        seconds = max(0, int(float(value)))
    except (TypeError, ValueError):
        return ""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} ч {minutes} мин"
    if minutes:
        return f"{minutes} мин {seconds} сек"
    return f"{seconds} сек"


def open_observer_history(parent, manager):
    """Browse local events; show full clipboard text and focus duration."""
    dialog = tk.Toplevel(parent)
    dialog.title("GigaAM — История наблюдателя")
    dialog.geometry("1100x720")
    dialog.minsize(800, 520)
    dialog.transient(parent)

    status_var = tk.StringVar()
    columns = ("time", "name", "duration", "path")
    tree = ttk.Treeview(dialog, columns=columns, show="headings", height=13)
    headings = {
        "time": ("Последнее изменение", 165),
        "name": ("Программа / объект", 260),
        "duration": ("Активность", 120),
        "path": ("Путь", 420),
    }
    for key, (label, width) in headings.items():
        tree.heading(key, text=label)
        tree.column(key, width=width, minwidth=65, anchor="w")
    tree.pack(fill="both", expand=True, padx=12, pady=(8, 4))

    detail_frame = ttk.LabelFrame(dialog, text="Содержимое события", padding=8)
    detail_frame.pack(fill="both", expand=True, padx=12, pady=5)
    detail_text = tk.Text(detail_frame, height=7, wrap="word")
    detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=detail_text.yview)
    detail_text.configure(yscrollcommand=detail_scroll.set, state="disabled")
    detail_scroll.pack(side="right", fill="y")
    detail_text.pack(side="left", fill="both", expand=True)

    def show_details(_event=None):
        selection = tree.selection()
        if not selection:
            return
        event_id = int(selection[0])
        event = next((item for item in manager.store.list_events(limit=500)
                      if int(item["id"]) == event_id), None)
        if event is None:
            return
        details = event.get("details") or {}
        if event.get("category") == "clipboard":
            history = details.get("history") or []
            if history:
                chunks = []
                for index, item in enumerate(history, 1):
                    copied_at = item.get("copied_at", "")
                    try:
                        copied_at = datetime.fromisoformat(copied_at).astimezone().strftime("%d.%m.%Y %H:%M:%S")
                    except (ValueError, TypeError):
                        pass
                    chunks.append(f"--- Копирование {index} · {copied_at} ---\\n{item.get('text', '')}")
                body = "\\n\\n".join(chunks)
            else:
                body = details.get("text") or "Текст отсутствует в этой записи."
            heading = f"Буфер обмена · записей: {len(history) or details.get('copies', 1)}"
        elif event.get("category") == "focus":
            titles = details.get("window_titles") or ([details.get("window_title")] if details.get("window_title") else [])
            body = (
                f"Программа: {event.get('object_name') or ''}\\n"
                f"Суммарная активность: {_format_duration(details.get('duration_seconds'))}\\n"
                f"Количество сеансов: {details.get('sessions', 1)}\\n"
                f"Последний PID: {details.get('last_pid', details.get('pid', ''))}\\n"
                f"Заголовки окон: {'; '.join(titles)}"
            )
            heading = "Суммарная активность приложения"
        elif event.get("category") == "apps":
            body = (
                f"Программа: {event.get('object_name') or ''}\\n"
                f"Запусков: {details.get('starts', 0)}\\n"
                f"Завершений: {details.get('stops', 0)}"
            )
            heading = "Статистика запусков программы"
        else:
            heading = "Подробности события"
            body = json.dumps(details, ensure_ascii=False, indent=2) if details else (
                event.get("object_path") or event.get("object_name") or "Нет дополнительных данных."
            )
        detail_frame.configure(text=heading)
        detail_text.configure(state="normal")
        detail_text.delete("1.0", "end")
        detail_text.insert("1.0", body)
        detail_text.configure(state="disabled")

    tree.bind("<<TreeviewSelect>>", show_details)

    def filtered_events():
        return manager.store.list_events(limit=500)

    def refresh_rows():
        selected = tree.selection()
        selected_id = selected[0] if selected else None
        for item in tree.get_children():
            tree.delete(item)
        events = filtered_events()
        for event in events:
            raw_time = event.get("occurred_at", "")
            try:
                stamp = datetime.fromisoformat(raw_time).astimezone().strftime("%d.%m.%Y %H:%M:%S")
            except (ValueError, TypeError):
                stamp = raw_time
            details = event.get("details") or {}
            duration = _format_duration(details.get("duration_seconds")) if event.get("category") == "focus" else ""
            name = event.get("object_name") or ""
            if event.get("category") == "clipboard":
                name = "Буфер обмена"
            elif event.get("category") == "apps":
                name = f"{name} · запусков: {details.get('starts', 0)}"
            if event.get("category") == "files":
                name = name + " · изменений: " + str(details.get("changes", 1))
            tree.insert("", "end", iid=str(event["id"]), values=(
                stamp, name, duration, event.get("object_path") or "",
            ))
        status_var.set(
            f"Показано: {len(events)} из последних 500 · Всего в базе: {manager.store.count_events()}"
        )
        if selected_id and tree.exists(selected_id):
            tree.selection_set(selected_id)
            show_details()

    def refresh():
        refresh_rows()
        dialog.after(3000, refresh)

    def export_csv():
        filename = filedialog.asksaveasfilename(
            parent=dialog, title="Экспорт истории", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile="gigaam_observer_history.csv",
        )
        if not filename:
            return
        events = filtered_events()
        with open(filename, "w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, extrasaction="ignore", fieldnames=[
                "id", "occurred_at", "category", "event_type", "source",
                "object_name", "object_path", "details",
            ])
            writer.writeheader()
            for event in events:
                row = dict(event)
                row["details"] = json.dumps(row.pop("details", {}), ensure_ascii=False)
                writer.writerow(row)
        messagebox.showinfo("Экспорт готов", f"Сохранено событий: {len(events)}", parent=dialog)

    def add_note():
        note = note_entry.get().strip()
        if not note:
            messagebox.showwarning("Пустая заметка", "Введите текст заметки.", parent=dialog)
            return
        selection = tree.selection()
        related = int(selection[0]) if selection else None
        manager.store.add_note(note, related_event_id=related)
        manager.store.add_event(
            "voice", "manual_note", "user",
            object_name=note[:160],
            details={"related_event_id": related} if related else {},
        )
        note_entry.delete(0, "end")
        refresh_rows()
        messagebox.showinfo("Заметка сохранена", "Заметка записана локально.", parent=dialog)

    toolbar = ttk.Frame(dialog, padding=(12, 8, 12, 0))
    toolbar.pack(fill="x")
    ttk.Button(toolbar, text="Обновить", command=refresh_rows).pack(side="left")
    ttk.Button(toolbar, text="Экспорт CSV", command=export_csv).pack(side="right")
    ttk.Label(dialog, textvariable=status_var, padding=(12, 2)).pack(anchor="w")

    note_frame = ttk.LabelFrame(dialog, text="Личная заметка (останется на этом компьютере)", padding=8)
    note_frame.pack(fill="x", padx=12, pady=(4, 8))
    note_entry = ttk.Entry(note_frame)
    note_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
    ttk.Button(note_frame, text="Сохранить заметку", command=add_note).pack(side="right")
    ttk.Label(
        dialog,
        text="Выберите событие перед заметкой, чтобы связать их; без выбора заметка будет самостоятельной.",
        padding=(12, 0, 12, 8),
    ).pack(anchor="w")

    refresh()
    dialog.grab_set()
    dialog.wait_window()
