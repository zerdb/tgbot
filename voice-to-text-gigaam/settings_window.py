"""Central settings UI. Secrets remain in environment variables, never JSON."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox

from agent_core import load_settings, save_settings
from dialog_utils import activate_modal


def open_settings_window(parent):
    if parent is None:
        return

    def show():
        if not parent.winfo_exists():
            return
        window = tk.Toplevel(parent)
        window.title("Настройки GigaAM")
        window.geometry("620x520")
        window.minsize(540, 440)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Единые настройки помощника", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Пароли и API-ключи не сохраняются в файл настроек. Используются переменные окружения Windows.", wraplength=570).pack(anchor="w", pady=(4, 12))
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
            var = tk.StringVar(value=str(values.get(key, "")))
            ttk.Entry(frame, textvariable=var).pack(fill="x", pady=(2, 8))
            vars_[key] = var
        remember = tk.BooleanVar(value=bool(values.get("remember_chat_history", True)))
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

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="Сохранить", command=save).pack(side="left")
        ttk.Button(buttons, text="Закрыть", command=window.destroy).pack(side="right")
        activate_modal(window, parent)

    parent.after(0, show)
