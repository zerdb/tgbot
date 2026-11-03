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
    "voice": "Заметки",
    "printing": "Печать",
    "usb": "USB",
    "browser": "Браузер",
}


def open_observer_history(parent, manager):
    """Open a read-only event browser with local CSV export and manual notes."""
    dialog = tk.Toplevel(parent)
    dialog.title("GigaAM — История наблюдателя")
    dialog.geometry("980x560")
    dialog.minsize(760, 420)
    dialog.transient(parent)

    category_var = tk.StringVar(value="Все события")
    status_var = tk.StringVar()
    selected_id = tk.StringVar()
    columns = ("time", "category", "event", "name", "path")
    tree = ttk.Treeview(dialog, columns=columns, show="headings", height=17)
    headings = {
        "time": ("Время", 155), "category": ("Категория", 100),
        "event": ("Событие", 145), "name": ("Объект", 210),
        "path": ("Путь", 340),
    }
    for key, (label, width) in headings.items():
        tree.heading(key, text=label)
        tree.column(key, width=width, minwidth=70, anchor="w")
    tree.pack(fill="both", expand=True, padx=12, pady=(8, 4))

    def selected_event_id():
        selection = tree.selection()
        return int(selection[0]) if selection else None

    def refresh():
        for item in tree.get_children():
            tree.delete(item)
        choice = category_var.get()
        category = next((key for key, label in CATEGORY_LABELS.items() if label == choice), None)
        events = manager.store.list_events(limit=500, category=category)
        for event in events:
            raw_time = event.get("occurred_at", "")
            try:
                stamp = datetime.fromisoformat(raw_time).astimezone().strftime("%d.%m.%Y %H:%M:%S")
            except (ValueError, TypeError):
                stamp = raw_time
            tree.insert("", "end", iid=str(event["id"]), values=(
                stamp, CATEGORY_LABELS.get(event["category"], event["category"]),
                event["event_type"], event.get("object_name") or "",
                event.get("object_path") or "",
            ))
        status_var.set(f"Показано: {len(events)} из последних 500 · Всего в базе: {manager.store.count_events()}")
        dialog.after(3000, refresh)

    def export_csv():
        filename = filedialog.asksaveasfilename(
            parent=dialog, title="Экспорт истории", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile="gigaam_observer_history.csv",
        )
        if not filename:
            return
        choice = category_var.get()
        category = next((key for key, label in CATEGORY_LABELS.items() if label == choice), None)
        events = manager.store.list_events(limit=1000, category=category)
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
        related = selected_event_id()
        manager.store.add_note(note, related_event_id=related)
        manager.record_event(
            "voice", "manual_note", "user",
            object_name=note[:160],
            details={"related_event_id": related} if related else {},
        )
        note_entry.delete(0, "end")
        refresh_now()
        messagebox.showinfo("Заметка сохранена", "Заметка записана локально.", parent=dialog)

    def refresh_now():
        # Cancel the pending timer by refreshing the visible rows immediately;
        # the periodic callback remains harmless and will refresh again.
        for item in tree.get_children():
            tree.delete(item)
        choice = category_var.get()
        category = next((key for key, label in CATEGORY_LABELS.items() if label == choice), None)
        events = manager.store.list_events(limit=500, category=category)
        for event in events:
            raw_time = event.get("occurred_at", "")
            try:
                stamp = datetime.fromisoformat(raw_time).astimezone().strftime("%d.%m.%Y %H:%M:%S")
            except (ValueError, TypeError):
                stamp = raw_time
            tree.insert("", "end", iid=str(event["id"]), values=(
                stamp, CATEGORY_LABELS.get(event["category"], event["category"]),
                event["event_type"], event.get("object_name") or "",
                event.get("object_path") or "",
            ))
        status_var.set(f"Показано: {len(events)} из последних 500 · Всего в базе: {manager.store.count_events()}")

    toolbar = ttk.Frame(dialog, padding=(12, 8, 12, 0))
    toolbar.pack(fill="x")
    ttk.Label(toolbar, text="Фильтр:").pack(side="left")
    filter_box = ttk.Combobox(toolbar, textvariable=category_var, state="readonly",
                              values=["Все события", *CATEGORY_LABELS.values()], width=16)
    filter_box.pack(side="left", padx=(6, 12))
    filter_box.bind("<<ComboboxSelected>>", lambda _event: refresh_now())
    ttk.Button(toolbar, text="Обновить", command=refresh_now).pack(side="left")
    ttk.Button(toolbar, text="Экспорт CSV", command=export_csv).pack(side="right")
    ttk.Label(dialog, textvariable=status_var, padding=(12, 2)).pack(anchor="w")

    note_frame = ttk.LabelFrame(dialog, text="Личная заметка (останется на этом компьютере)", padding=8)
    note_frame.pack(fill="x", padx=12, pady=(4, 12))
    note_entry = ttk.Entry(note_frame)
    note_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
    ttk.Button(note_frame, text="Сохранить заметку", command=add_note).pack(side="right")
    ttk.Label(dialog, text="Выберите событие перед заметкой, чтобы связать их; без выбора заметка будет самостоятельной.",
              padding=(12, 0, 12, 8)).pack(anchor="w")

    refresh()
    dialog.grab_set()
    dialog.wait_window()
