"""Full local address book with editable contacts."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk, messagebox

from email_manager import load_address_book, save_address_book
from dialog_utils import activate_modal


def open_contact_form(parent=None, start_new=False):
    """Open the shared address book; add, edit and delete contact records."""
    if parent is None:
        print("Для открытия контактов требуется главное окно приложения.")
        return

    def show():
        if not parent.winfo_exists():
            return
        root = tk.Toplevel(parent)
        root.title("Адресная книга — контакты")
        root.geometry("820x540")
        root.minsize(680, 440)
        root.attributes("-topmost", True)

        outer = ttk.Frame(root, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Мои контакты", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Общий справочник для писем и голосовых команд").pack(anchor="w", pady=(2, 10))

        columns = ("name", "phone", "email", "notes")
        table_frame = ttk.Frame(outer)
        table_frame.pack(fill="both", expand=True)
        table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        for key, title, width in (
            ("name", "Имя", 170), ("phone", "Телефон", 135),
            ("email", "Электронная почта", 230), ("notes", "Заметка", 190),
        ):
            table.heading(key, text=title)
            table.column(key, width=width, minwidth=90, anchor="w")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        editor = ttk.LabelFrame(outer, text="Карточка контакта", padding=10)
        editor.pack(fill="x", pady=(10, 8))
        vars_ = {key: tk.StringVar(master=root) for key in columns}
        labels = (("name", "Имя"), ("phone", "Телефон"), ("email", "Почта"), ("notes", "Заметка"))
        for index, (key, title) in enumerate(labels):
            ttk.Label(editor, text=title).grid(row=0, column=index, sticky="w", padx=(0, 8))
            entry = ttk.Entry(editor, textvariable=vars_[key], width=(24 if key in ("name", "email") else 17))
            entry.grid(row=1, column=index, sticky="ew", padx=(0, 8))
            editor.columnconfigure(index, weight=1)

        status = tk.StringVar(master=root, value="")
        ttk.Label(outer, textvariable=status).pack(anchor="w")

        def records():
            return load_address_book()

        def refresh(select_name=None):
            table.delete(*table.get_children())
            for name, item in sorted(records().items(), key=lambda pair: pair[0].casefold()):
                table.insert("", "end", iid=name, values=(
                    name, item.get("phone", ""), item.get("email", ""), item.get("notes", "")
                ))
            status.set(f"Контактов: {len(table.get_children())}")
            if select_name and table.exists(select_name):
                table.selection_set(select_name)
                table.focus(select_name)
                table.see(select_name)

        def clear_editor():
            for var in vars_.values():
                var.set("")
            table.selection_remove(table.selection())

        def selected(_event=None):
            selection = table.selection()
            if not selection:
                return
            name = selection[0]
            item = records().get(name, {})
            vars_["name"].set(name)
            for key in ("phone", "email", "notes"):
                vars_[key].set(item.get(key, ""))

        def save():
            name = vars_["name"].get().strip()
            phone = vars_["phone"].get().strip()
            email = vars_["email"].get().strip()
            notes = vars_["notes"].get().strip()
            if not name:
                messagebox.showwarning("Не указано имя", "Заполни имя контакта.", parent=root)
                return
            if email and not re.fullmatch(r"[\w.+-]+@[\w.-]+\.[a-zа-я]{2,}", email, re.IGNORECASE):
                messagebox.showwarning("Неверная почта", "Проверь адрес электронной почты.", parent=root)
                return
            book = records()
            selection = table.selection()
            old_name = selection[0] if selection else None
            if old_name and old_name != name:
                book.pop(old_name, None)
            book[name] = {"phone": phone, "email": email, "notes": notes}
            try:
                save_address_book(book)
            except OSError as exc:
                messagebox.showerror("Ошибка сохранения", str(exc), parent=root)
                return
            refresh(name)
            status.set(f"Контакт «{name}» сохранён")

        def delete():
            selection = table.selection()
            if not selection:
                messagebox.showinfo("Контакт не выбран", "Выбери контакт в таблице.", parent=root)
                return
            name = selection[0]
            if not messagebox.askyesno("Удалить контакт", f"Удалить контакт «{name}»?", parent=root):
                return
            book = records()
            book.pop(name, None)
            try:
                save_address_book(book)
            except OSError as exc:
                messagebox.showerror("Ошибка сохранения", str(exc), parent=root)
                return
            clear_editor()
            refresh()
            status.set(f"Контакт «{name}» удалён")

        table.bind("<<TreeviewSelect>>", selected)
        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Новый контакт", command=clear_editor).pack(side="left")
        ttk.Button(controls, text="Сохранить / изменить", command=save).pack(side="left", padx=8)
        ttk.Button(controls, text="Удалить", command=delete).pack(side="left")
        ttk.Button(controls, text="Закрыть", command=root.destroy).pack(side="right")
        refresh()
        if start_new:
            # Голосовое добавление открывает ту же адресную книгу,
            # но сразу переводит пользователя в режим новой карточки.
            clear_editor()
            name_entry = editor.grid_slaves(row=1, column=0)
            if name_entry:
                name_entry[0].focus_set()
            status.set("Новая карточка: заполни имя, телефон, почту и заметку")
        root.bind("<Escape>", lambda _event: root.destroy())
        activate_modal(root, parent)

    try:
        parent.after(0, show)
    except tk.TclError as exc:
        print(f"Не удалось открыть адресную книгу: {exc}")
