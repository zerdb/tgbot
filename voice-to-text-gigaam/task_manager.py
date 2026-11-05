"""Small persistent task planner linked to the GigaAM assistant."""
from __future__ import annotations

import json
import os
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox

from dialog_utils import activate_modal

DATA_PATH = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "GigaAMVoiceAssistant" / "tasks.json"


def load_tasks():
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_tasks(items):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(DATA_PATH)


def open_task_manager(parent):
    if parent is None:
        return

    def show():
        if not parent.winfo_exists():
            return
        window = tk.Toplevel(parent)
        window.title("Задачи и планы")
        window.geometry("760x520")
        window.minsize(620, 420)
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Мои задачи", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Срок указывай в формате ГГГГ-ММ-ДД ЧЧ:ММ (можно оставить пустым).").pack(anchor="w", pady=(3, 8))
        table = ttk.Treeview(frame, columns=("task", "due", "state"), show="headings", selectmode="browse")
        for key, title, width in (("task", "Задача", 390), ("due", "Срок", 160), ("state", "Статус", 100)):
            table.heading(key, text=title)
            table.column(key, width=width)
        table.pack(fill="both", expand=True)
        form = ttk.Frame(frame)
        form.pack(fill="x", pady=10)
        task_var, due_var = tk.StringVar(), tk.StringVar()
        ttk.Label(form, text="Задача").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=task_var, width=48).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(form, text="Срок").grid(row=0, column=1, sticky="w")
        ttk.Entry(form, textvariable=due_var, width=22).grid(row=1, column=1, sticky="ew")
        form.columnconfigure(0, weight=1)
        items = load_tasks()

        def refresh():
            table.delete(*table.get_children())
            for index, item in enumerate(items):
                table.insert("", "end", iid=str(index), values=(item.get("title", ""), item.get("due", ""), "Готово" if item.get("done") else "В работе"))

        def add():
            title = task_var.get().strip()
            due = due_var.get().strip()
            if not title:
                messagebox.showwarning("Задачи", "Введи название задачи.", parent=window)
                return
            if due:
                try:
                    datetime.strptime(due, "%Y-%m-%d %H:%M")
                except ValueError:
                    messagebox.showwarning("Формат срока", "Используй ГГГГ-ММ-ДД ЧЧ:ММ.", parent=window)
                    return
            items.append({"title": title, "due": due, "done": False, "created_at": datetime.now().isoformat(timespec="seconds")})
            save_tasks(items)
            task_var.set(""); due_var.set("")
            refresh()

        def toggle():
            selection = table.selection()
            if not selection:
                return
            item = items[int(selection[0])]
            item["done"] = not bool(item.get("done"))
            save_tasks(items); refresh()

        def delete():
            selection = table.selection()
            if not selection:
                return
            if not messagebox.askyesno("Удалить задачу", "Удалить выбранную задачу?", parent=window):
                return
            items.pop(int(selection[0]))
            save_tasks(items); refresh()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Добавить", command=add).pack(side="left")
        ttk.Button(buttons, text="Готово / вернуть", command=toggle).pack(side="left", padx=8)
        ttk.Button(buttons, text="Удалить", command=delete).pack(side="left")
        ttk.Button(buttons, text="Закрыть", command=window.destroy).pack(side="right")
        refresh()
        activate_modal(window, parent)

    parent.after(0, show)
