"""Tkinter form for manually adding an email contact."""
from __future__ import annotations

import re
from tkinter import ttk, messagebox
import tkinter as tk

from email_manager import load_address_book, save_address_book

def open_contact_form(parent=None):
    """Open a desktop form to add a contact to the local address book."""
    def show():
        if parent is None or not parent.winfo_exists():
            print("Главное окно закрыто: форму контактов открыть нельзя.")
            return

        root = tk.Toplevel(parent)
        root.title("Добавить контакт")
        root.geometry("420x210")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Имя контакта").grid(row=0, column=0, sticky="w", pady=(0, 5))
        name_entry = ttk.Entry(frame, width=42)
        name_entry.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(frame, text="Электронная почта").grid(row=2, column=0, sticky="w", pady=(0, 5))
        email_entry = ttk.Entry(frame, width=42)
        email_entry.grid(row=3, column=0, sticky="ew", pady=(0, 14))

        def save():
            name = name_entry.get().strip()
            address = email_entry.get().strip()
            if not name:
                messagebox.showwarning("Не заполнено имя", "Укажи имя контакта.", parent=root)
                name_entry.focus_set()
                return
            if not re.fullmatch(r"[\w.+-]+@[\w.-]+\.[a-zа-я]{2,}", address, re.IGNORECASE):
                messagebox.showwarning("Неверный адрес", "Проверь электронную почту.", parent=root)
                email_entry.focus_set()
                return
            book = load_address_book()
            book[name] = address
            try:
                save_address_book(book)
            except OSError as exc:
                messagebox.showerror("Ошибка сохранения", str(exc), parent=root)
                return
            messagebox.showinfo("Контакт сохранён", f"{name} — {address}", parent=root)
            root.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, sticky="e")
        ttk.Button(buttons, text="Отмена", command=root.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Сохранить", command=save).pack(side="right")
        root.bind("<Return>", lambda _event: save())
        name_entry.focus_set()
        root.update_idletasks()
        root.lift()
        root.focus_force()
        root.transient(parent)
        root.lift()
        root.focus_force()

    if parent is None:
        print("Для открытия контактов требуется главное окно приложения.")
        return
    try:
        show()
    except tk.TclError as exc:
        print(f"Не удалось открыть форму контактов: {exc}")

