"""Unified manager window for notes, tasks and reminders."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from dialog_utils import center_window, apply_modern_style


def open_reminders(parent):
    from reminders import list_items, add_note, add_reminder, update_item, complete_item, delete_item

    win = tk.Toplevel(parent)
    apply_modern_style(win)
    win.title("Zero Control — заметки и дела")
    win.geometry("900x680")
    win.minsize(620, 440)
    center_window(win, parent)

    footer = ttk.Frame(win, padding=(14, 8, 14, 12))
    footer.pack(side="bottom", fill="x")
    frame = ttk.Frame(win, padding=14)
    frame.pack(side="top", fill="both", expand=True)

    ttk.Label(frame, text="Заметки и дела", font=("Segoe UI", 17, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Синие — заметки   •   Оранжевые — напоминания   •   Зелёные — выполненные",
        wraplength=820,
    ).pack(anchor="w", pady=(3, 10))

    filter_var = tk.StringVar(master=win, value="Все")
    filter_row = ttk.Frame(frame)
    filter_row.pack(fill="x", pady=(0, 8))
    ttk.Label(filter_row, text="Показать:").pack(side="left")
    filter_box = ttk.Combobox(
        filter_row, textvariable=filter_var,
        values=("Все", "Активные", "Выполненные"),
        state="readonly", width=14,
    )
    filter_box.pack(side="left", padx=(5, 12))

    list_shell = ttk.Frame(frame)
    list_shell.pack(fill="both", expand=True)
    scrollbar = ttk.Scrollbar(list_shell, orient="vertical")
    listing = tk.Text(
        list_shell, wrap="word", font=("Segoe UI", 9),
        background="#ffffff", foreground="#172033",
        relief="flat", borderwidth=0, padx=12, pady=7,
        spacing1=1, spacing2=1, spacing3=2,
        yscrollcommand=scrollbar.set, cursor="arrow",
        selectbackground="#bfdbfe", selectforeground="#172033",
    )
    scrollbar.configure(command=listing.yview)
    listing.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    listing.tag_configure("note", foreground="#1d4ed8", background="#eff6ff",
                          lmargin1=10, lmargin2=10, rmargin=10, spacing1=3, spacing3=2)
    listing.tag_configure("reminder", foreground="#b45309", background="#fff7ed",
                          lmargin1=10, lmargin2=10, rmargin=10, spacing1=4, spacing3=2)
    listing.tag_configure("done", foreground="#15803d", background="#f0fdf4",
                          lmargin1=10, lmargin2=10, rmargin=10, spacing1=8, spacing3=2)
    listing.tag_configure("body", foreground="#172033", font=("Segoe UI", 9),
                          lmargin1=18, lmargin2=18, rmargin=12, spacing1=1, spacing3=2)
    listing.tag_configure("selected", background="#dbeafe")
    listing.tag_configure("empty", foreground="#64748b", font=("Segoe UI", 9))

    selected_id = {"value": None}
    item_map = {}
    current_items = []

    def select_item(item_id):
        selected_id["value"] = item_id
        listing.tag_remove("selected", "1.0", "end")
        tag = item_map.get(item_id, {}).get("tag")
        if tag:
            listing.tag_add("selected", f"1.0", "end")
            listing.tag_remove("selected", "1.0", "end")
            listing.tag_add("selected", f"{tag}.first", f"{tag}.last")

    def selected():
        item_id = selected_id["value"]
        return next((item for item in current_items if item["id"] == item_id), None)

    def refresh():
        nonlocal current_items
        selected_id["value"] = None
        item_map.clear()
        current_items = [
            item for item in list_items(True)
            if not (filter_var.get() == "Активные" and item["completed"])
            and not (filter_var.get() == "Выполненные" and not item["completed"])
        ]
        listing.configure(state="normal")
        listing.delete("1.0", "end")

        if not current_items:
            listing.insert("end", "Здесь пока пусто. Нажми «Новая запись», чтобы добавить заметку или дело.\n", "empty")
            listing.configure(state="disabled")
            return

        for index, item in enumerate(current_items):
            due = "Без срока"
            if item.get("due_at"):
                try:
                    due = datetime.fromisoformat(item["due_at"]).strftime("%d.%m.%Y в %H:%M")
                except (TypeError, ValueError):
                    due = "Некорректная дата"
            status = "Выполнено" if item["completed"] else (
                "Напоминание" if item.get("due_at") else "Заметка"
            )
            tag = f"item_{index}"
            color_tag = "done" if item["completed"] else ("reminder" if item.get("due_at") else "note")
            start = listing.index("end")
            listing.insert("end", f"  {status}     •     {due}\n", (color_tag, tag))
            listing.insert("end", f"  {item['text']}\n", ("body", tag))
            end = listing.index("end")
            item_map[item["id"]] = {"tag": tag, "start": start, "end": end}
            listing.tag_bind(tag, "<Button-1>", lambda _event, iid=item["id"]: select_item(iid))
            listing.tag_bind(tag, "<Double-Button-1>", lambda _event, iid=item["id"]: (
                select_item(iid), edit_dialog(next(x for x in current_items if x["id"] == iid))
            ))
        listing.configure(state="disabled")
        listing.yview_moveto(0)

    def edit_dialog(item=None):
        dialog = tk.Toplevel(win)
        apply_modern_style(dialog)
        dialog.title("Изменить запись" if item else "Новая запись")
        dialog.transient(win)
        dialog.grab_set()
        dialog.geometry("620x410")
        dialog.minsize(440, 300)

        # Закрепляем нижнюю панель до размещения растягиваемой области.
        row = ttk.Frame(dialog, padding=(14, 8, 14, 14))
        row.pack(side="bottom", fill="x")
        body = ttk.Frame(dialog, padding=14)
        body.pack(side="top", fill="both", expand=True)
        ttk.Label(body, text="Текст заметки или дела").pack(anchor="w")
        text_box = tk.Text(
            body, height=9, wrap="word", font=("Segoe UI", 10),
            undo=True, padx=8, pady=7,
        )
        text_box.pack(fill="both", expand=True, pady=(4, 10))
        if item:
            text_box.insert("1.0", item["text"])

        ttk.Label(body, text="Время напоминания (необязательно)").pack(anchor="w")
        due_var = tk.StringVar(master=dialog)
        if item and item.get("due_at"):
            try:
                due_var.set(datetime.fromisoformat(item["due_at"]).strftime("%d.%m.%Y %H:%M"))
            except ValueError:
                pass
        ttk.Entry(body, textvariable=due_var).pack(fill="x", pady=(4, 3))
        ttk.Label(
            body,
            text="Примеры: «через 20 минут», «завтра в 9». Пустое поле — обычная заметка.",
            wraplength=560,
        ).pack(anchor="w")

        def save():
            value = text_box.get("1.0", "end").strip()
            due = due_var.get().strip()
            if not value:
                messagebox.showwarning("Запись", "Введи текст.", parent=dialog)
                return
            if due and not (
                due.startswith("через ") or due.startswith("завтра")
                or (len(due) == 16 and due[2] == "." and due[5] == ".")
            ):
                messagebox.showwarning(
                    "Время",
                    "Используй «через 20 минут», «завтра в 9» или дату ДД.ММ.ГГГГ ЧЧ:ММ.",
                    parent=dialog,
                )
                return
            if item:
                ok = update_item(item["id"], value, due)
            elif due:
                ok = add_reminder("напомни " + due + " " + value)
            else:
                ok = add_note(value)
            if not ok:
                messagebox.showwarning(
                    "Запись", "Не удалось сохранить запись или распознать срок.", parent=dialog
                )
                return
            dialog.destroy()
            refresh()

        ttk.Button(row, text="Сохранить", command=save).pack(side="right")
        ttk.Button(row, text="Отмена", command=dialog.destroy).pack(side="right", padx=6)
        center_window(dialog, win)
        text_box.focus_set()

    def mark_done():
        item = selected()
        if not item:
            messagebox.showinfo("Выполнение", "Сначала выбери запись.", parent=win)
            return
        if complete_item(item["id"]):
            refresh()

    def remove():
        item = selected()
        if not item:
            messagebox.showinfo("Удаление", "Сначала выбери запись.", parent=win)
            return
        if messagebox.askyesno(
            "Удалить", "Удалить выбранную запись без возможности восстановления?", parent=win
        ):
            delete_item(item["id"])
            refresh()

    buttons = ttk.Frame(footer)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="＋ Новая запись", command=lambda: edit_dialog()).pack(side="left")
    ttk.Button(
        buttons, text="Изменить",
        command=lambda: edit_dialog(selected()) if selected() else messagebox.showinfo(
            "Изменение", "Сначала выбери запись.", parent=win
        ),
    ).pack(side="left", padx=5)
    ttk.Button(buttons, text="✓ Выполнено", command=mark_done).pack(side="left")
    ttk.Button(buttons, text="Удалить", command=remove).pack(side="left", padx=5)
    ttk.Button(buttons, text="Обновить", command=refresh).pack(side="right")

    filter_box.bind("<<ComboboxSelected>>", lambda _event: refresh())
    refresh()
