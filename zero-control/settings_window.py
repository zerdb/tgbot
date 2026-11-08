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
)
from dialog_utils import activate_modal


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
        shell = ttk.Frame(window, padding=4)
        shell.pack(fill="both", expand=True)
        footer = ttk.Frame(shell)
        footer.pack(side="bottom", fill="x", pady=(5, 0))
        ttk.Separator(shell, orient="horizontal").pack(side="bottom", fill="x", pady=(4, 0))
        content_area = ttk.Frame(shell)
        content_area.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(content_area, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(content_area, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        frame = ttk.Frame(canvas, padding=(4, 2, 4, 6))
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
        ttk.Label(frame, text="Единые настройки помощника", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Ключ Groq и доступ к камере хранятся в защищённом хранилище Windows.", wraplength=570).pack(anchor="w", pady=(2, 6))
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

        groq_box = ttk.LabelFrame(frame, text="Groq — основная ИИ-модель", padding=6)
        groq_box.pack(fill="x", pady=(1, 4))
        groq_var = tk.StringVar(master=window)
        ttk.Entry(groq_box, textvariable=groq_var, show="*").pack(fill="x", pady=(0, 3))
        groq_status = tk.StringVar(
            master=window,
            value="Ключ сохранён" if (os.getenv("GROQ_API_KEY", "").strip() or get_groq_api_key()) else "Ключ не задан",
        )
        ttk.Label(groq_box, textvariable=groq_status).pack(anchor="w", pady=(0, 2))
        def save_groq_secret():
            try:
                set_groq_api_key(groq_var.get())
                groq_var.set("")
                groq_status.set("Ключ сохранён в защищённом хранилище Windows")
                messagebox.showinfo("Groq", "Ключ сохранён. Перезапусти помощника для применения.", parent=window)
            except Exception as exc:
                messagebox.showerror("Groq", str(exc), parent=window)
        def clear_groq_secret():
            try:
                delete_groq_api_key()
                groq_var.set("")
                groq_status.set("Ключ не задан — облачная модель недоступна")
            except Exception as exc:
                messagebox.showerror("Groq", str(exc), parent=window)
        groq_box_buttons = ttk.Frame(groq_box)
        groq_box_buttons.pack(fill="x", pady=(1, 0))
        ttk.Button(groq_box_buttons, text="Сохранить ключ", command=save_groq_secret).pack(side="left")
        ttk.Button(groq_box_buttons, text="Очистить", command=clear_groq_secret).pack(side="left", padx=(6, 0))

        camera_box = ttk.LabelFrame(frame, text="Доступ к камере", padding=6)
        camera_box.pack(fill="x", pady=(1, 4))
        camera_var = tk.StringVar(master=window)
        ttk.Entry(camera_box, textvariable=camera_var, show="*").pack(fill="x", pady=(0, 3))
        camera_status = tk.StringVar(master=window, value="Сохранено" if get_camera_password() else "Не сохранено")
        ttk.Label(camera_box, textvariable=camera_status).pack(anchor="w", pady=(0, 2))
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
        camera_box_buttons = ttk.Frame(camera_box)
        camera_box_buttons.pack(fill="x", pady=(1, 0))
        ttk.Button(camera_box_buttons, text="Сохранить", command=save_camera_secret).pack(side="left")
        ttk.Button(camera_box_buttons, text="Очистить", command=clear_camera_secret).pack(side="left", padx=(6, 0))

        moondream_box = ttk.LabelFrame(frame, text="Moondream — резервная ИИ-модель помощника и камеры", padding=6)
        moondream_box.pack(fill="x", pady=(1, 4))
        moondream_var = tk.StringVar(master=window)
        ttk.Entry(moondream_box, textvariable=moondream_var, show="*").pack(fill="x", pady=(0, 3))
        moondream_status = tk.StringVar(master=window, value="Ключ сохранён" if get_moondream_api_key() else "Ключ не задан")
        ttk.Label(moondream_box, textvariable=moondream_status).pack(anchor="w", pady=(0, 2))
        def save_moondream_secret():
            try:
                set_moondream_api_key(moondream_var.get())
                moondream_var.set("")
                moondream_status.set("Ключ сохранён в защищённом хранилище Windows")
                messagebox.showinfo("Moondream", "Ключ сохранён. Moondream останется резервной моделью помощника и камеры.", parent=window)
            except Exception as exc:
                messagebox.showerror("Moondream", str(exc), parent=window)
        def clear_moondream_secret():
            try:
                delete_moondream_api_key()
                moondream_var.set("")
                moondream_status.set("Ключ не задан — резервная модель недоступна")
            except Exception as exc:
                messagebox.showerror("Moondream", str(exc), parent=window)
        moondream_box_buttons = ttk.Frame(moondream_box)
        moondream_box_buttons.pack(fill="x", pady=(1, 0))
        ttk.Button(moondream_box_buttons, text="Сохранить ключ", command=save_moondream_secret).pack(side="left")
        ttk.Button(moondream_box_buttons, text="Очистить", command=clear_moondream_secret).pack(side="left", padx=(6, 0))

        remember = tk.BooleanVar(master=window, value=bool(values.get("remember_chat_history", True)))
        ttk.Checkbutton(frame, text="Сохранять историю диалога ИИ на этом компьютере", variable=remember).pack(anchor="w", pady=(1, 4))
        clean_dictation = tk.BooleanVar(master=window, value=bool(values.get("clean_dictation_with_ai", False)))
        ttk.Checkbutton(frame, text="Очищать текст диктовки с помощью ИИ", variable=clean_dictation).pack(anchor="w", pady=(1, 4))
        status = (
            "Ключ Groq: сохранён" if (os.getenv("GROQ_API_KEY", "").strip() or get_groq_api_key())
            else "Ключ Groq: не задан"
        ) + " · " + ("Пароль почты: настроен" if os.getenv("ZERO_CONTROL_MAIL_PASSWORD", os.getenv("GIGAAM_MAIL_PASSWORD")) else "Пароль почты: не настроен")
        ttk.Label(frame, text=status, wraplength=570).pack(anchor="w", pady=(2, 6))

        def save():
            payload = {key: var.get() for key, var in vars_.items()}
            payload["remember_chat_history"] = remember.get()
            payload["clean_dictation_with_ai"] = clean_dictation.get()
            try:
                save_settings(payload)
            except OSError as exc:
                messagebox.showerror("Настройки", f"Не удалось сохранить настройки: {exc}", parent=window)
                return
            messagebox.showinfo("Настройки", "Настройки сохранены. Перезапусти помощника для применения ко всем модулям.", parent=window)
            window.destroy()

        memory = ttk.LabelFrame(frame, text="Память помощника", padding=6)
        memory.pack(fill="x", pady=(3, 5))
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
        memory_buttons.pack(fill="x", pady=(3, 0))
        ttk.Button(memory_buttons, text="Запомнить заметку…", command=add_memory).pack(side="left")
        ttk.Button(memory_buttons, text="Очистить заметки", command=clear_memory).pack(side="left", padx=8)
        def clear_history():
            if messagebox.askyesno("Очистить историю", "Удалить сохранённую историю диалога ИИ?", parent=window):
                clear_chat_history()
                messagebox.showinfo("История", "История диалога очищена.", parent=window)
        ttk.Button(memory_buttons, text="Очистить историю", command=clear_history).pack(side="left", padx=8)
        buttons = footer
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Сохранить", command=save).pack(side="left")
        ttk.Button(buttons, text="Закрыть", command=window.destroy).pack(side="right")
        activate_modal(window, parent)

    parent.after(0, show)
