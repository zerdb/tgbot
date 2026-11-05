"""Central settings UI. Secrets remain in environment variables, never JSON."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from agent_core import load_settings, save_settings, remember_note, forget_notes, clear_chat_history, get_camera_password, set_camera_password, delete_camera_password, get_moondream_api_key, set_moondream_api_key, delete_moondream_api_key
from dialog_utils import activate_modal


def open_settings_window(parent):
    if parent is None:
        return

    def show():
        if not parent.winfo_exists():
            return
        window = tk.Toplevel(parent)
        window.title("Настройки GigaAM")
        window.geometry("680x760")
        window.minsize(580, 680)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Единые настройки помощника", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(frame, text="API-ключи берутся из переменных окружения. Камерный доступ хранится в защищённом хранилище Windows.", wraplength=570).pack(anchor="w", pady=(4, 12))
        values = load_settings()
        fields = [
            ("openrouter_model", "Модель OpenRouter"),
            ("openrouter_base_url", "Адрес API"),
            ("mail_login", "Почтовый логин"),
            ("imap_host", "IMAP-сервер"),
            ("imap_port", "IMAP-порт"),
        ]
        vars_ = {}
        for key, label in fields:
            ttk.Label(frame, text=label).pack(anchor="w")
            var = tk.StringVar(master=window, value=str(values.get(key, "")))
            ttk.Entry(frame, textvariable=var).pack(fill="x", pady=(2, 8))
            vars_[key] = var

        camera_box = ttk.LabelFrame(frame, text="Доступ к камере", padding=8)
        camera_box.pack(fill="x", pady=(2, 8))
        camera_var = tk.StringVar(master=window)
        ttk.Entry(camera_box, textvariable=camera_var, show="*").pack(side="left", fill="x", expand=True, padx=(0, 8))
        camera_status = tk.StringVar(master=window, value="Сохранено" if get_camera_password() else "Не сохранено")
        ttk.Label(camera_box, textvariable=camera_status).pack(anchor="w", pady=(6, 0))
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
                camera_status.set("Не сохранено")
            except Exception as exc:
                messagebox.showerror("Камера", str(exc), parent=window)
        ttk.Button(camera_box, text="Сохранить", command=save_camera_secret).pack(side="left")
        ttk.Button(camera_box, text="Очистить", command=clear_camera_secret).pack(side="left", padx=6)

        moondream_box = ttk.LabelFrame(frame, text="Moondream — резервная ИИ-модель помощника и камеры", padding=8)
        moondream_box.pack(fill="x", pady=(2, 8))
        moondream_var = tk.StringVar(master=window)
        ttk.Entry(moondream_box, textvariable=moondream_var, show="*").pack(side="left", fill="x", expand=True, padx=(0, 8))
        moondream_status = tk.StringVar(master=window, value="Ключ сохранён" if get_moondream_api_key() else "Ключ не задан")
        ttk.Label(moondream_box, textvariable=moondream_status).pack(anchor="w", pady=(6, 0))
        def save_moondream_secret():
            try:
                set_moondream_api_key(moondream_var.get())
                moondream_var.set("")
                moondream_status.set("Ключ сохранён в защищённом хранилище Windows")
                messagebox.showinfo("Moondream", "Ключ сохранён. Если OpenRouter будет недоступен, помощник автоматически попробует Moondream.", parent=window)
            except Exception as exc:
                messagebox.showerror("Moondream", str(exc), parent=window)
        def clear_moondream_secret():
            try:
                delete_moondream_api_key()
                moondream_var.set("")
                moondream_status.set("Ключ не задан — резервная модель недоступна")
            except Exception as exc:
                messagebox.showerror("Moondream", str(exc), parent=window)
        ttk.Button(moondream_box, text="Сохранить ключ", command=save_moondream_secret).pack(side="left")
        ttk.Button(moondream_box, text="Очистить", command=clear_moondream_secret).pack(side="left", padx=6)

        remember = tk.BooleanVar(master=window, value=bool(values.get("remember_chat_history", True)))
        ttk.Checkbutton(frame, text="Сохранять историю диалога ИИ на этом компьютере", variable=remember).pack(anchor="w", pady=(2, 8))
        status = (
            "OpenRouter API key: настроен" if os.getenv("OPENROUTER_API_KEY") else "OpenRouter API key: не настроен"
        ) + " · " + ("Пароль почты: настроен" if os.getenv("GIGAAM_MAIL_PASSWORD") else "Пароль почты: не настроен")
        ttk.Label(frame, text=status, wraplength=570).pack(anchor="w", pady=(4, 12))

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

        memory = ttk.LabelFrame(frame, text="Память помощника", padding=8)
        memory.pack(fill="x", pady=(6, 10))
        ttk.Label(memory, text="В память попадают только заметки, которые ты явно попросишь сохранить.").pack(anchor="w")
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
        memory_buttons = ttk.Frame(memory)
        memory_buttons.pack(fill="x", pady=(5, 0))
        ttk.Button(memory_buttons, text="Запомнить заметку…", command=add_memory).pack(side="left")
        ttk.Button(memory_buttons, text="Очистить заметки", command=clear_memory).pack(side="left", padx=8)
        def clear_history():
            if messagebox.askyesno("Очистить историю", "Удалить сохранённую историю диалога ИИ?", parent=window):
                clear_chat_history()
                messagebox.showinfo("История", "История диалога очищена.", parent=window)
        ttk.Button(memory_buttons, text="Очистить историю", command=clear_history).pack(side="left", padx=8)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="Сохранить", command=save).pack(side="left")
        ttk.Button(buttons, text="Закрыть", command=window.destroy).pack(side="right")
        activate_modal(window, parent)

    parent.after(0, show)
