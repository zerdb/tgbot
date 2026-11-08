"""Central settings UI. API secrets are stored in Windows Credential Manager, never JSON."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from agent_core import (
    load_settings, save_settings, remember_note, forget_notes, clear_chat_history,
    get_camera_password, set_camera_password, delete_camera_password,
    get_moondream_api_key, set_moondream_api_key, delete_moondream_api_key,
    get_groq_api_key, set_groq_api_key, delete_groq_api_key,
    get_mail_password, set_mail_password,
)
from dialog_utils import activate_modal, apply_modern_style

BG = "#F4F6FB"
SURFACE = "#FFFFFF"
TEXT = "#172033"
MUTED = "#7B8497"
ACCENT = "#5146D8"
BORDER = "#E6E9F2"


def open_settings_window(parent):
    if parent is None:
        return

    def show():
        if not parent.winfo_exists():
            return
        window = tk.Toplevel(parent)
        window.title("Настройки Zero Control")
        window.geometry("600x620")
        window.minsize(480, 420)
        apply_modern_style(window)
        style = ttk.Style(window)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("Card.TLabel", background=SURFACE, foreground=TEXT,
                        font=("Segoe UI", 9))
        style.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED,
                        font=("Segoe UI", 8))
        style.configure("CardTitle.TLabel", background=SURFACE, foreground=TEXT,
                        font=("Segoe UI", 10, "bold"))
        style.configure("Card.TButton", background="#F8F9FC", foreground=TEXT,
                        bordercolor=BORDER, padding=(9, 6),
                        font=("Segoe UI", 9, "bold"))
        style.map("Card.TButton", background=[("active", "#F0EFFF")],
                  foreground=[("active", ACCENT)])
        shell = ttk.Frame(window, padding=10)
        shell.pack(fill="both", expand=True)
        footer = ttk.Frame(shell)
        footer.pack(side="bottom", fill="x", pady=(5, 0))
        ttk.Separator(shell, orient="horizontal").pack(side="bottom", fill="x", pady=(4, 0))
        content_area = ttk.Frame(shell)
        content_area.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(content_area, highlightthickness=0, borderwidth=0, bg=BG)
        scrollbar = ttk.Scrollbar(content_area, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        frame = ttk.Frame(canvas, padding=(5, 4, 5, 8))
        frame_window = canvas.create_window((0, 0), window=frame, anchor="nw")
        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(frame_window, width=canvas.winfo_width())
        frame.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)
        def on_mousewheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        window.bind("<Destroy>", lambda event: canvas.unbind_all("<MouseWheel>") if event.widget is window else None, add="+")
        ttk.Label(frame, text="Единые настройки помощника",
                  font=("Segoe UI", 15, "bold"), foreground=TEXT).pack(anchor="w")
        ttk.Label(frame, text="Ключи и доступы защищены средствами Windows.",
                  wraplength=570, foreground=MUTED).pack(anchor="w", pady=(3, 12))
        def make_card(parent, title):
            card = tk.Frame(parent, bg=SURFACE, highlightthickness=1,
                            highlightbackground=BORDER, bd=0)
            card.pack(fill="x", pady=(0, 9))
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(
                anchor="w", padx=12, pady=(10, 5))
            body = ttk.Frame(card, style="Card.TFrame", padding=(12, 2, 12, 11))
            body.pack(fill="x")
            return body
        values = load_settings()
        fields = [
            ("groq_model", "Модель Groq"),
            ("mail_login", "Почтовый логин"),
            ("imap_host", "IMAP-сервер"),
            ("imap_port", "IMAP-порт"),
        ]
        vars_ = {}
        for key, label in fields:
            ttk.Label(frame, text=label).pack(anchor="w")
            var = tk.StringVar(master=window, value=str(values.get(key, "")))
            ttk.Entry(frame, textvariable=var).pack(fill="x", pady=(0, 2))
            vars_[key] = var

        keys_box = make_card(frame, "API-ключи и доступы")

        secret_vars = {}
        secret_setters = {
            "Groq:": set_groq_api_key,
            "Камера:": set_camera_password,
            "Moondream:": set_moondream_api_key,
        }

        def show_paste_menu(event, entry, paste_callback):
            menu = tk.Menu(window, tearoff=False)
            menu.add_command(label="Вставить", command=paste_callback)
            menu.add_command(label="Выделить всё", command=lambda: (entry.focus_set(), entry.select_range(0, "end")))
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        def add_secret_row(label, getter):
            row = ttk.Frame(keys_box, style="Card.TFrame")
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label, width=13, style="Card.TLabel").pack(side="left")
            value = tk.StringVar(master=window)
            entry = ttk.Entry(row, textvariable=value, show="*", width=1)
            entry.pack(side="left", fill="x", expand=True, padx=(3, 5))

            def paste_secret(_event=None, target=entry, variable=value):
                try:
                    clipboard_text = window.clipboard_get()
                    target.focus_set()
                    target.delete(0, "end")
                    target.insert(0, clipboard_text)
                    variable.set(clipboard_text)
                except tk.TclError:
                    messagebox.showwarning(
                        "Буфер обмена",
                        "В буфере обмена нет доступного текста.",
                        parent=window,
                    )
                return "break"

            entry.bind("<Control-v>", paste_secret)
            entry.bind("<Control-V>", paste_secret)
            entry.bind("<Shift-Insert>", paste_secret)
            entry.bind("<Button-3>", lambda event, target=entry, paste=paste_secret: show_paste_menu(event, target, paste))
            state = "ключ уже сохранён" if getter() else "ключ не задан"
            ttk.Label(row, text=state, width=18, style="CardMuted.TLabel").pack(side="right")
            secret_vars[label] = value

        add_secret_row("Groq:", get_groq_api_key)
        add_secret_row("Камера:", get_camera_password)
        add_secret_row("Moondream:", get_moondream_api_key)
        add_secret_row("Пароль почты:", get_mail_password)
        secret_setters["Пароль почты:"] = set_mail_password
        ttk.Label(
            keys_box,
            text="Новые ключи сохраняются только кнопкой «Сохранить» внизу.",
            wraplength=520, style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        remember = tk.BooleanVar(master=window, value=bool(values.get("remember_chat_history", True)))
        ttk.Checkbutton(frame, text="Сохранять историю диалога ИИ на этом компьютере", variable=remember).pack(anchor="w", pady=(1, 4))
        clean_dictation = tk.BooleanVar(master=window, value=bool(values.get("clean_dictation_with_ai", False)))
        ttk.Checkbutton(frame, text="Очищать текст диктовки с помощью ИИ", variable=clean_dictation).pack(anchor="w", pady=(1, 4))

        learning = make_card(frame, "Обучение локальной маршрутизации")
        ttk.Label(
            learning,
            text="Просматривай команды, распознанные ИИ, проверяй действие и параметры и добавляй подтверждённые фразы в локальные правила.",
            wraplength=540, style="Card.TLabel",
        ).pack(anchor="w")
        def open_intent_learning():
            from local_intents_window import open_recognized_intents_window
            open_recognized_intents_window(window)
        ttk.Button(
            learning,
            text="Распознанные намерения…",
            command=open_intent_learning, style="Card.TButton",
        ).pack(anchor="w", pady=(8, 0))
        status = (
            "Ключ Groq: сохранён" if (os.getenv("GROQ_API_KEY", "").strip() or get_groq_api_key())
            else "Ключ Groq: не задан"
        ) + " · " + ("Пароль почты: настроен" if (os.getenv("ZERO_CONTROL_MAIL_PASSWORD", os.getenv("GIGAAM_MAIL_PASSWORD")) or get_mail_password()) else "Пароль почты: не настроен")
        ttk.Label(frame, text=status, wraplength=570).pack(anchor="w", pady=(2, 6))

        def save():
            payload = {key: var.get() for key, var in vars_.items()}
            payload["remember_chat_history"] = remember.get()
            payload["clean_dictation_with_ai"] = clean_dictation.get()
            try:
                for label, value in secret_vars.items():
                    secret = value.get().strip()
                    if secret:
                        secret_setters[label](secret)
                save_settings(payload)
            except Exception as exc:
                messagebox.showerror("Настройки", f"Не удалось сохранить настройки: {exc}", parent=window)
                return
            messagebox.showinfo("Настройки", "Настройки сохранены. Перезапусти помощника для применения ко всем модулям.", parent=window)
            window.destroy()

        memory = make_card(frame, "Память помощника")
        ttk.Label(memory, text="В память попадают только заметки, которые ты явно попросишь сохранить.",
                  style="Card.TLabel", wraplength=530).pack(anchor="w")
        def add_memory():
            note = simpledialog.askstring("Память помощника", "Что помощник должен помнить?", parent=window)
            if note and note.strip():
                try:
                    remember_note(note)
                    messagebox.showinfo("Память", "Заметка сохранена локально.", parent=window)
                except OSError as exc:
                    messagebox.showerror("Память", str(exc), parent=window)
        def clear_memory():
            if messagebox.askyesno("Очистить память", "Удалить сохранённые заметки памяти? История диалога останется.", parent=window):
                forget_notes()
                messagebox.showinfo("Память", "Сохранённые заметки очищены.", parent=window)
        memory_buttons = ttk.Frame(memory, style="Card.TFrame")
        memory_buttons.pack(fill="x", pady=(3, 0))
        ttk.Button(memory_buttons, text="Запомнить заметку…", command=add_memory,
                   style="Card.TButton").pack(side="left")
        ttk.Button(memory_buttons, text="Очистить заметки", command=clear_memory,
                   style="Card.TButton").pack(side="left", padx=8)
        def clear_history():
            if messagebox.askyesno("Очистить историю", "Удалить сохранённую историю диалога ИИ?", parent=window):
                clear_chat_history()
                messagebox.showinfo("История", "История диалога очищена.", parent=window)
        ttk.Button(memory_buttons, text="Очистить историю", command=clear_history,
                   style="Card.TButton").pack(side="left", padx=8)
        buttons = footer
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Сохранить", command=save).pack(side="left")
        ttk.Button(buttons, text="Закрыть", command=window.destroy).pack(side="right")
        activate_modal(window, parent)

    parent.after(0, show)
