"""Minimal settings for GigaAM Observer; clipboard is the only opt-in."""
from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk

from observer.observer_config import save_config


def open_observer_settings(parent, manager):
    current = copy.deepcopy(manager.config)
    dialog = tk.Toplevel(parent)
    dialog.title("GigaAM — Наблюдатель")
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.grab_set()

    clipboard_var = tk.BooleanVar(
        value=bool(current.get("categories", {}).get("clipboard", False))
    )

    outer = ttk.Frame(dialog, padding=18)
    outer.pack(fill="both", expand=True)
    ttk.Label(
        outer, text="Локальный наблюдатель",
        font=("Segoe UI", 15, "bold"),
    ).pack(anchor="w")
    ttk.Label(
        outer,
        text=(
            "Наблюдатель автоматически запускается вместе с помощником. "
            "Он фиксирует изменения файлов в выбранных папках, запуск и "
            "завершение программ, а также активное окно и длительность работы "
            "в нём. Содержимое документов, нажатия клавиш и экран не записываются."
        ),
        wraplength=470, justify="left",
    ).pack(anchor="w", pady=(8, 12))

    group = ttk.LabelFrame(outer, text="Дополнительная функция", padding=10)
    group.pack(fill="x", pady=(0, 10))
    ttk.Checkbutton(
        group,
        text="Собирать текст буфера обмена (распознаваемые секреты отбрасываются)",
        variable=clipboard_var,
    ).pack(anchor="w")

    watched = current.get("watched_folders", [])
    folders_text = "\n".join(str(item) for item in watched) or "Список папок пока пуст."
    ttk.Label(outer, text="Отслеживаемые папки:", foreground="#444444").pack(
        anchor="w", pady=(4, 2)
    )
    ttk.Label(outer, text=folders_text, wraplength=470, justify="left").pack(anchor="w")

    ttk.Label(
        outer,
        text=(
            "История хранится локально без автоматического удаления. "
            "Буфер обмена по умолчанию выключен. При включении отбрасываются "
            "тексты, похожие на пароли, токены и другие секреты; фильтр не "
            "гарантирует распознавание всех чувствительных данных. "
            "Передача данных внешнему ИИ выключена."
        ),
        wraplength=470, justify="left",
    ).pack(anchor="w", pady=(10, 12))

    buttons = ttk.Frame(outer)
    buttons.pack(fill="x")

    def save_and_close():
        updated = copy.deepcopy(current)
        updated["enabled"] = True
        updated["start_with_assistant"] = True
        updated["created_with_consent"] = True
        categories = updated.setdefault("categories", {})
        categories.update({
            "files": True,
            "apps": True,
            "focus": True,
            "clipboard": bool(clipboard_var.get()),
            "printing": False,
            "usb": False,
        })
        categories.pop("browser", None)
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
