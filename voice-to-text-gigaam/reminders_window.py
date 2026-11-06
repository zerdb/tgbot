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
    win.geometry("860x650")
    win.minsize(620, 440)
    center_window(win, parent)

    frame = ttk.Frame(win, padding=14)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="Заметки и дела", font=("Segoe UI", 17, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Заметки и задачи отображаются отдельными карточками. Длинный текст переносится на новые строки.",
        wraplength=780,
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

    # A canvas-backed card list replaces Treeview: Treeview rows have a fixed
    # height and cannot display multi-line note text reliably.
    list_shell = ttk.Frame(frame)
    list_shell.pack(fill="both", expand=True)
    canvas = tk.Canvas(list_shell, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(list_shell, orient="vertical", command=canvas.yview)
    cards_frame = ttk.Frame(canvas)
    cards_window = canvas.create_window((0, 0), window=cards_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    selected_id = {"value": None}
    card_widgets = {}

    def update_scroll_region(_event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def update_cards_width(event):
        canvas.itemconfigure(cards_window, width=event.width)

    cards_frame.bind("<Configure>", update_scroll_region)
    canvas.bind("<Configure>", update_cards_width)

    def select_card(item_id):
        selected_id["value"] = item_id
        for current_id, widgets in card_widgets.items():
            color = "#e7f0fb" if current_id == item_id else "#f3f4f6"
            for widget in widgets:
                try:
                    widget.configure(background=color)
                except tk.TclError:
                    pass

    def selected():
        item_id = selected_id["value"]
        return next((item for item in current_items if item["id"] == item_id), None)

    current_items = []

    def refresh():
        nonlocal current_items
        for child in cards_frame.winfo_children():
            child.destroy()
        card_widgets.clear()
        selected_id["value"] = None
        current_items = []
        for item in list_items(True):
            if filter_var.get() == "Активные" and item["completed"]:
                continue
            if filter_var.get() == "Выполненные" and not item["completed"]:
                continue
            current_items.append(item)

        if not current_items:
            ttk.Label(
                cards_frame, text="Здесь пока пусто. Нажми «Новая запись», чтобы добавить заметку или дело.",
                wraplength=650, justify="left",
            ).pack(anchor="w", padx=12, pady=18)
            return

        for item in current_items:
            due = "Без срока"
            if item.get("due_at"):
                try:
                    due = datetime.fromisoformat(item["due_at"]).strftime("%d.%m.%Y в %H:%M")
                except ValueError:
                    due = "Некорректная дата"
            status = "Выполнено" if item["completed"] else (
                "Напоминание" if item.get("due_at") else "Заметка"
            )

            card = tk.Frame(cards_frame, background="#f3f4f6", padx=12, pady=9,
                            highlightthickness=1, highlightbackground="#d5d9df")
            card.pack(fill="x", padx=3, pady=4)
            meta = tk.Label(
                card, text=f"{status}   •   {due}", anchor="w",
                font=("Segoe UI", 9, "bold"), foreground="#475569",
                background="#f3f4f6",
            )
            meta.pack(fill="x", anchor="w")
            note = tk.Label(
                card, text=item["text"], anchor="w", justify="left",
                font=("Segoe UI", 10), foreground="#172033",
                background="#f3f4f6", wraplength=700,
            )
            note.pack(fill="x", anchor="w", pady=(5, 0))
            widgets = [card, meta, note]
            card_widgets[item["id"]] = widgets
            for widget in widgets:
                widget.bind("<Button-1>", lambda _event, iid=item["id"]: select_card(iid))
                widget.bind("<Double-Button-1>", lambda _event, iid=item["id"]: (
                    select_card(iid), edit_dialog(next(x for x in current_items if x["id"] == iid))
                ))
            note.bind("<Configure>", lambda event, label=note: label.configure(
                wraplength=max(220, event.width)
            ))
        update_scroll_region()

    def edit_dialog(item=None):
        dialog = tk.Toplevel(win)
        apply_modern_style(dialog)
        dialog.title("Изменить запись" if item else "Новая запись")
        dialog.transient(win)
        dialog.grab_set()
        dialog.geometry("600x390")
        dialog.minsize(440, 300)

        body = ttk.Frame(dialog, padding=14)
        body.pack(fill="both", expand=True)
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
            wraplength=540,
        ).pack(anchor="w")

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(12, 0))

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

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(9, 0))
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

    def on_mousewheel(event):
        if getattr(event, "delta", 0):
            canvas.yview_scroll(int(-event.delta / 120), "units")

    canvas.bind("<MouseWheel>", on_mousewheel)
    cards_frame.bind("<MouseWheel>", on_mousewheel)
    refresh()
