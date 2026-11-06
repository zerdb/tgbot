"""Современное окно настроек Zero Control на стандартном Tkinter/ttk."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from agent_core import (
    load_settings, save_settings, remember_note, forget_notes,
    clear_chat_history, get_camera_password, set_camera_password,
    delete_camera_password, get_moondream_api_key,
    set_moondream_api_key, delete_moondream_api_key,
)
from dialog_utils import activate_modal


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
        window.geometry("660x690")
        window.minsize(580, 500)
        window.configure(bg=BG)

        style = ttk.Style(window)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("App.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 9))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=SURFACE, foreground=TEXT, font=("Segoe UI", 9))
        style.configure("Heading.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 17, "bold"))
        style.configure("CardTitle.TLabel", background=SURFACE, foreground=TEXT, font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", padding=(7, 4), fieldbackground="#FFFFFF",
                        foreground=TEXT, bordercolor=BORDER, lightcolor=BORDER,
                        darkcolor=BORDER, insertcolor=TEXT)
        style.configure("TCheckbutton", background=SURFACE, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", SURFACE)])
        style.configure("TButton", font=("Segoe UI", 9), padding=(9, 5),
                        background="#FFFFFF", foreground=TEXT, bordercolor=BORDER)
        style.map("TButton", background=[("active", "#F0EFFF")],
                  foreground=[("active", ACCENT)])
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"),
                        padding=(16, 9), background=ACCENT, foreground="#FFFFFF",
                        borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#4338CA"), ("pressed", "#3730A3")],
                  foreground=[("active", "#FFFFFF")])

        values = load_settings()
        vars_ = {}

        # Верхняя часть окна остаётся неподвижной, прокручивается только содержимое.
        header = ttk.Frame(window, style="App.TFrame", padding=(16, 10, 16, 8))
        header.pack(fill="x")
        ttk.Label(header, text="Настройки", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Параметры Zero Control, подключение сервисов и данные помощника.",
            style="Muted.TLabel", wraplength=650,
        ).pack(anchor="w", pady=(4, 0))

        content_host = tk.Frame(window, bg=BG)
        content_host.pack(fill="both", expand=True, padx=16)
        canvas = tk.Canvas(content_host, bg=BG, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(content_host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        content = ttk.Frame(canvas, style="App.TFrame")
        content_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(content_id, width=canvas.winfo_width())
        content.bind("<Configure>", update_scroll)
        canvas.bind("<Configure>", update_scroll)

        def wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        def card(title, hint=None):
            outer = tk.Frame(content, bg=SURFACE, highlightthickness=1,
                             highlightbackground=BORDER, bd=0)
            outer.pack(fill="x", pady=(0, 8))
            inner = ttk.Frame(outer, style="Card.TFrame", padding=(11, 8))
            inner.pack(fill="x")
            ttk.Label(inner, text=title, style="CardTitle.TLabel").pack(anchor="w")
            if hint:
                ttk.Label(inner, text=hint, style="Card.TLabel",
                          wraplength=590).pack(anchor="w", pady=(2, 5))
            return inner

        def add_field(container, key, label):
            index = len(vars_)
            cell = ttk.Frame(container, style="Card.TFrame")
            cell.grid(row=index // 2, column=index % 2, sticky="ew",
                      padx=(0 if index % 2 == 0 else 10, 0), pady=3)
            ttk.Label(cell, text=label, style="Card.TLabel").pack(anchor="w", pady=(1, 2))
            var = tk.StringVar(master=window, value=str(values.get(key, "")))
            ttk.Entry(cell, textvariable=var).pack(fill="x")
            vars_[key] = var

        general = card("Подключение и почта",
                       "Основные параметры API и почтового подключения.")
        general.columnconfigure(0, weight=1)
        general.columnconfigure(1, weight=1)
        for key, label in [
            ("openrouter_model", "Модель OpenRouter"),
            ("openrouter_base_url", "Адрес API"),
            ("mail_login", "Почтовый логин"),
            ("imap_host", "IMAP-сервер"),
            ("imap_port", "IMAP-порт"),
        ]:
            add_field(general, key, label)

        camera = card("Камера", "Пароль хранится в защищённом хранилище Windows.")
        camera_var = tk.StringVar(master=window)
        ttk.Label(camera, text="Пароль камеры", style="Card.TLabel").pack(anchor="w", pady=(4, 3))
        camera_row = ttk.Frame(camera, style="Card.TFrame")
        camera_row.pack(fill="x")
        ttk.Entry(camera_row, textvariable=camera_var, show="*").pack(side="left", fill="x", expand=True, padx=(0, 8))
        camera_status = tk.StringVar(master=window, value="Пароль сохранён" if get_camera_password() else "Пароль не сохранён")
        ttk.Label(camera, textvariable=camera_status, style="Card.TLabel").pack(anchor="w", pady=(4, 0))

        def save_camera_secret():
            try:
                set_camera_password(camera_var.get())
                camera_var.set("")
                camera_status.set("Сохранено в защищённом хранилище Windows")
                messagebox.showinfo("Камера", "Данные доступа сохранены.", parent=window)
            except Exception as exc:
                messagebox.showerror("Камера", str(exc), parent=window)

        def clear_camera_secret():
            try:
                delete_camera_password()
                camera_var.set("")
                camera_status.set("Пароль не сохранён")
            except Exception as exc:
                messagebox.showerror("Камера", str(exc), parent=window)

        ttk.Button(camera_row, text="Сохранить пароль", command=save_camera_secret).pack(side="left")
        ttk.Button(camera_row, text="Очистить", command=clear_camera_secret).pack(side="left", padx=(7, 0))

        moondream = card("Резервная ИИ-модель",
                         "Moondream используется как запасная модель помощника и камеры.")
        moondream_var = tk.StringVar(master=window)
        ttk.Label(moondream, text="API-ключ Moondream", style="Card.TLabel").pack(anchor="w", pady=(4, 3))
        moon_row = ttk.Frame(moondream, style="Card.TFrame")
        moon_row.pack(fill="x")
        ttk.Entry(moon_row, textvariable=moondream_var, show="*").pack(side="left", fill="x", expand=True, padx=(0, 8))
        moondream_status = tk.StringVar(master=window, value="Ключ сохранён" if get_moondream_api_key() else "Ключ не задан")
        ttk.Label(moondream, textvariable=moondream_status, style="Card.TLabel").pack(anchor="w", pady=(4, 0))

        def save_moondream_secret():
            try:
                set_moondream_api_key(moondream_var.get())
                moondream_var.set("")
                moondream_status.set("Ключ сохранён в защищённом хранилище Windows")
                messagebox.showinfo("Moondream", "Ключ сохранён. При недоступности OpenRouter помощник попробует резервную модель.", parent=window)
            except Exception as exc:
                messagebox.showerror("Moondream", str(exc), parent=window)

        def clear_moondream_secret():
            try:
                delete_moondream_api_key()
                moondream_var.set("")
                moondream_status.set("Ключ не задан — резервная модель недоступна")
            except Exception as exc:
                messagebox.showerror("Moondream", str(exc), parent=window)

        ttk.Button(moon_row, text="Сохранить ключ", command=save_moondream_secret).pack(side="left")
        ttk.Button(moon_row, text="Очистить", command=clear_moondream_secret).pack(side="left", padx=(7, 0))

        privacy = card("История диалога")
        remember = tk.BooleanVar(master=window, value=bool(values.get("remember_chat_history", True)))
        ttk.Checkbutton(privacy, text="Сохранять историю диалога ИИ на этом компьютере",
                        variable=remember).pack(anchor="w", pady=(4, 2))

        api_status = (
            "OpenRouter API key: настроен" if os.getenv("OPENROUTER_API_KEY") else "OpenRouter API key: не настроен"
        ) + "   ·   " + (
            "Пароль почты: настроен" if os.getenv("GIGAAM_MAIL_PASSWORD") else "Пароль почты: не настроен"
        )
        ttk.Label(privacy, text=api_status, style="Card.TLabel",
                  wraplength=610).pack(anchor="w", pady=(5, 0))

        memory = card("Память помощника",
                      "В память попадают только заметки, которые ты явно попросишь сохранить.")
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

        def clear_history():
            if messagebox.askyesno("Очистить историю", "Удалить сохранённую историю диалога ИИ?", parent=window):
                clear_chat_history()
                messagebox.showinfo("История", "История диалога очищена.", parent=window)

        memory_actions = ttk.Frame(memory, style="Card.TFrame")
        memory_actions.pack(fill="x", pady=(5, 0))
        ttk.Button(memory_actions, text="Запомнить заметку…", command=add_memory).pack(side="left")
        ttk.Button(memory_actions, text="Очистить заметки", command=clear_memory).pack(side="left", padx=(7, 0))
        ttk.Button(memory_actions, text="Очистить историю", command=clear_history).pack(side="left", padx=(7, 0))

        def save():
            payload = {key: var.get() for key, var in vars_.items()}
            payload["remember_chat_history"] = remember.get()
            try:
                save_settings(payload)
            except OSError as exc:
                messagebox.showerror("Настройки", f"Не удалось сохранить настройки: {exc}", parent=window)
                return
            messagebox.showinfo("Настройки", "Настройки сохранены. Перезапусти помощника для применения ко всем модулям.", parent=window)
            window.destroy()

        # Нижняя панель не прокручивается и всегда остаётся видимой.
        footer = tk.Frame(window, bg=SURFACE, highlightthickness=1,
                          highlightbackground=BORDER, bd=0)
        footer.pack(side="bottom", fill="x")
        footer_inner = ttk.Frame(footer, style="Card.TFrame", padding=(14, 7))
        footer_inner.pack(fill="x")
        ttk.Button(footer_inner, text="Закрыть", command=window.destroy).pack(side="right")
        ttk.Button(footer_inner, text="Сохранить", style="Primary.TButton",
                   command=save).pack(side="right", padx=(0, 8))

        activate_modal(window, parent)

    parent.after(0, show)
