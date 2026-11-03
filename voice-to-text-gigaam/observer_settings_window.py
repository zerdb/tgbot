"""User-facing, explicit controls for GigaAM Observer."""
from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk

from observer.observer_config import save_config


def open_observer_settings(parent, manager):
    """Show Observer settings; collectors change only after the user saves."""
    current = copy.deepcopy(manager.config)
    dialog = tk.Toplevel(parent)
    dialog.title("GigaAM — Наблюдатель")
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.grab_set()

    enabled_var = tk.BooleanVar(value=bool(current.get("enabled", False)))
    consent_var = tk.BooleanVar(value=bool(current.get("created_with_consent", False)))
    categories = current.setdefault("categories", {})
    files_var = tk.BooleanVar(value=bool(categories.get("files", False)))
    apps_var = tk.BooleanVar(value=bool(categories.get("apps", False)))

    outer = ttk.Frame(dialog, padding=18)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="Локальный наблюдатель", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    ttk.Label(
        outer,
        text=("Наблюдатель замечает выбранные системные события и хранит историю "
              "только на этом компьютере. Он не читает содержимое документов, "
              "не записывает клавиатуру, экран, буфер обмена или браузер."),
        wraplength=470, justify="left"
    ).pack(anchor="w", pady=(8, 12))

    ttk.Checkbutton(
        outer, text="Включить наблюдатель", variable=enabled_var
    ).pack(anchor="w", pady=(0, 8))

    group = ttk.LabelFrame(outer, text="Что разрешить отслеживать", padding=10)
    group.pack(fill="x", pady=(0, 10))
    ttk.Checkbutton(group, text="Файлы в выбранных папках (имя, путь и метаданные)",
                    variable=files_var).pack(anchor="w")
    ttk.Checkbutton(group, text="Запуск и завершение программ (имя, PID и путь)",
                    variable=apps_var).pack(anchor="w")
    watched = current.get("watched_folders", [])
    folders_text = "\\n".join(str(item) for item in watched) or "Папки не найдены — добавьте их в config.json."
    ttk.Label(group, text="Папки, которые проверяются на изменения:", foreground="#444444").pack(anchor="w", pady=(8, 2))
    ttk.Label(group, text=folders_text, wraplength=440, justify="left").pack(anchor="w")
    ttk.Label(group, text="Печать и USB пока не собираются; браузер намеренно исключён.",
              foreground="#666666").pack(anchor="w", pady=(6, 0))

    ttk.Label(
        outer,
        text=("При включении сбор событий начнётся только для отмеченных категорий. "
              "История хранится локально без автоматического удаления. "
              "Передача сводок внешнему ИИ сейчас не включена."),
        wraplength=470, justify="left"
    ).pack(anchor="w", pady=(0, 10))
    ttk.Checkbutton(
        outer, text="Я ознакомился и явно разрешаю сбор отмеченных событий.",
        variable=consent_var
    ).pack(anchor="w", pady=(0, 12))

    buttons = ttk.Frame(outer)
    buttons.pack(fill="x")

    def save_and_close():
        if enabled_var.get() and not consent_var.get():
            messagebox.showwarning(
                "Нужно согласие",
                "Чтобы включить наблюдатель, подтвердите согласие на сбор выбранных событий.",
                parent=dialog,
            )
            return
        updated = copy.deepcopy(current)
        updated["enabled"] = bool(enabled_var.get())
        updated["created_with_consent"] = bool(consent_var.get())
        updated.setdefault("categories", {})
        updated["categories"].update({
            "files": bool(files_var.get()),
            "apps": bool(apps_var.get()),
            "printing": False,
            "usb": False,
            "browser": False,
        })
        if not updated["enabled"]:
            updated["categories"]["files"] = False
            updated["categories"]["apps"] = False
        save_config(updated, manager.data_dir / "config.json")
        manager.stop()
        manager.config = updated
        manager.start()
        dialog.destroy()

    ttk.Button(buttons, text="Сохранить", command=save_and_close).pack(side="right")
    ttk.Button(buttons, text="Отмена", command=dialog.destroy).pack(side="right", padx=(0, 8))
    dialog.update_idletasks()
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - dialog.winfo_width()) // 2)
    y = parent.winfo_rooty() + max(0, (parent.winfo_height() - dialog.winfo_height()) // 2)
    dialog.geometry(f"+{x}+{y}")
    dialog.wait_window()
