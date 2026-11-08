"""Окно просмотра ИИ-намерений и ручного добавления точных локальных правил."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, messagebox

from dialog_utils import activate_modal
from intent_router import ACTIONS
from local_intents import list_records, promote_record, delete_record

_BLOCKED = {"ai_chat", "camera_question", "inspect_camera_image", "unknown"}


def open_recognized_intents_window(parent):
    if parent is None:
        return

    window = tk.Toplevel(parent)
    window.title("Распознанные намерения")
    window.geometry("900x610")
    window.minsize(680, 460)
    shell = ttk.Frame(window, padding=12)
    shell.pack(fill="both", expand=True)
    ttk.Label(shell, text="Распознанные намерения", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    ttk.Label(
        shell,
        text="Здесь сохраняются результаты семантической классификации. Выбери запись, проверь действие и параметры, затем добавь точную фразу в локальную маршрутизацию.",
        wraplength=850,
    ).pack(anchor="w", pady=(3, 9))

    body = ttk.Panedwindow(shell, orient="horizontal")
    body.pack(fill="both", expand=True)
    left = ttk.Frame(body, padding=(0, 0, 8, 0))
    right = ttk.Frame(body, padding=(8, 0, 0, 0))
    body.add(left, weight=1)
    body.add(right, weight=2)

    list_frame = ttk.Frame(left)
    list_frame.pack(fill="both", expand=True)
    records_list = tk.Listbox(list_frame, width=38, activestyle="dotbox", exportselection=False)
    scroll = ttk.Scrollbar(list_frame, orient="vertical", command=records_list.yview)
    records_list.configure(yscrollcommand=scroll.set)
    records_list.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    phrase_var = tk.StringVar(master=window)
    action_var = tk.StringVar(master=window)
    meta_var = tk.StringVar(master=window, value="Выбери запись слева.")
    ttk.Label(right, text="Исходная фраза (можно отредактировать)").pack(anchor="w")
    phrase_entry = ttk.Entry(right, textvariable=phrase_var)
    phrase_entry.pack(fill="x", pady=(2, 8))
    ttk.Label(right, text="Распознанное действие").pack(anchor="w")
    action_values = [name for name in ACTIONS if name not in _BLOCKED]
    action_box = ttk.Combobox(right, textvariable=action_var, values=action_values, state="readonly")
    action_box.pack(fill="x", pady=(2, 8))
    ttk.Label(right, text="Параметры (JSON; проверь перед добавлением)").pack(anchor="w")
    params_box = tk.Text(right, height=9, wrap="word", font=("Consolas", 9))
    params_box.pack(fill="both", expand=True, pady=(2, 8))
    ttk.Label(right, textvariable=meta_var, wraplength=540).pack(anchor="w", pady=(0, 8))

    records = []
    selected_id = None

    def refresh(select_id=None):
        nonlocal records, selected_id
        records = list_records()
        records_list.delete(0, "end")
        selected_id = None
        for item in records:
            intent = item.get("intent") or {}
            state = " · локально" if item.get("promoted") else ""
            records_list.insert("end", f"{item.get('phrase', '')[:42]}  →  {intent.get('action', 'unknown')}{state}")
        if select_id:
            for index, item in enumerate(records):
                if item.get("id") == select_id:
                    records_list.selection_set(index)
                    records_list.see(index)
                    show_selected()
                    break
        elif records:
            records_list.selection_set(0)
            show_selected()
        else:
            phrase_var.set("")
            action_var.set("")
            params_box.delete("1.0", "end")
            meta_var.set("Пока нет записей. Они появятся после команд, классифицированных через ИИ.")

    def show_selected(_event=None):
        nonlocal selected_id
        selection = records_list.curselection()
        if not selection:
            return
        item = records[selection[0]]
        selected_id = item.get("id")
        intent = item.get("intent") or {}
        phrase_var.set(item.get("phrase", ""))
        action = intent.get("action", "unknown")
        action_var.set(action if action in action_values else "")
        params_box.delete("1.0", "end")
        params_box.insert("1.0", json.dumps(intent.get("parameters") or {}, ensure_ascii=False, indent=2))
        confidence = intent.get("confidence", 0)
        meta_var.set(
            f"Источник: {item.get('provider', 'ИИ')} · Уверенность: {confidence:.2f} · "
            f"Тип: {intent.get('kind', '—')} · "
            f"{'Уже добавлено в локальные правила' if item.get('promoted') else 'Ещё не добавлено'}"
        )

    def promote():
        if not selected_id:
            messagebox.showinfo("Локальное правило", "Сначала выбери запись.", parent=window)
            return
        selected = next((item for item in records if item.get("id") == selected_id), None)
        intent = (selected or {}).get("intent") or {}
        if intent.get("kind") != "execute":
            messagebox.showwarning(
                "Нельзя добавить",
                "В локальные команды можно превращать только намерения типа execute. Ответы и уточнения требуют ИИ или дополнительного контекста.",
                parent=window,
            )
            return
        try:
            params = json.loads(params_box.get("1.0", "end").strip() or "{}")
            promote_record(selected_id, phrase_var.get(), action_var.get(), params)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            messagebox.showerror("Локальное правило", f"Проверь действие и JSON-параметры: {exc}", parent=window)
            return
        messagebox.showinfo(
            "Локальное правило",
            "Точная фраза добавлена в локальную маршрутизацию. Другие формулировки автоматически не угадываются.",
            parent=window,
        )
        refresh(selected_id)

    def remove():
        if not selected_id:
            return
        if not messagebox.askyesno("Удалить запись", "Удалить выбранную запись из журнала распознанных намерений?", parent=window):
            return
        delete_record(selected_id)
        refresh()

    records_list.bind("<<ListboxSelect>>", show_selected)
    controls = ttk.Frame(right)
    controls.pack(fill="x")
    ttk.Button(controls, text="Сделать локальным", command=promote).pack(side="left")
    ttk.Button(controls, text="Удалить запись", command=remove).pack(side="left", padx=(8, 0))
    ttk.Button(controls, text="Обновить", command=refresh).pack(side="right")
    ttk.Button(shell, text="Закрыть", command=window.destroy).pack(anchor="e", pady=(9, 0))
    refresh()
    activate_modal(window, parent)
