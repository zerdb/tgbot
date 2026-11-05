"""Full local address book with editable contacts."""
from __future__ import annotations

import json
import re
import threading
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

        def open_smart_import():
            dialog = tk.Toplevel(root)
            dialog.title("Умный импорт контактов")
            dialog.geometry("700x590")
            dialog.minsize(560, 440)
            dialog.transient(root)
            dialog.attributes("-topmost", True)
            frame = ttk.Frame(dialog, padding=14)
            frame.pack(fill="both", expand=True)
            ttk.Label(frame, text="Вставь текст с контактами", font=("Segoe UI", 13, "bold")).pack(anchor="w")
            ttk.Label(
                frame,
                text="Можно вставить список, подпись из письма или несколько строк с именами и email.",
                wraplength=650,
            ).pack(anchor="w", pady=(3, 8))
            source = tk.Text(frame, height=10, wrap="word", font=("Segoe UI", 10))
            source.pack(fill="both", expand=True)
            ttk.Label(frame, text="Результат распознавания").pack(anchor="w", pady=(10, 4))
            preview = ttk.Treeview(frame, columns=("name", "email", "phone", "notes"), show="headings", height=7)
            for key, title, width in (
                ("name", "Имя", 180), ("email", "Почта", 220),
                ("phone", "Телефон", 120), ("notes", "Заметка", 130),
            ):
                preview.heading(key, text=title)
                preview.column(key, width=width, minwidth=70)
            preview.pack(fill="both", expand=True)
            hint = tk.StringVar(master=dialog, value="После разбора проверь список и подтверди импорт.")
            ttk.Label(frame, textvariable=hint, wraplength=650).pack(anchor="w", pady=(6, 4))
            parsed_contacts = []

            def parse_with_ai():
                raw_text = source.get("1.0", "end").strip()
                if not raw_text:
                    messagebox.showinfo("Нет текста", "Сначала вставь текст с контактами.", parent=dialog)
                    return
                parse_button.configure(state="disabled")
                import_button.configure(state="disabled")
                hint.set("ИИ разбирает текст…")
                preview.delete(*preview.get_children())

                def worker():
                    try:
                        from ai_chat import ask_ai
                        prompt = (
                            "Извлеки из текста все контактные данные людей. Верни ТОЛЬКО корректный JSON-массив "
                            "объектов с полями name, email, phone, notes. Не выдумывай отсутствующие значения; "
                            "пустые поля заполняй пустой строкой. Имя отделяй от адреса почты. "
                            "Если в тексте несколько людей, верни каждого отдельным объектом. "
                            "Не добавляй в контакты подписи, должности и организации как отдельных людей, "
                            "если это не имя человека.\n\nТЕКСТ:\n" + raw_text[:12000]
                        )
                        answer = ask_ai(prompt)
                        match = re.search(r"\\[\\s\\S]*\\]", answer)
                        if not match:
                            raise ValueError("ИИ не вернул JSON-массив контактов.")
                        data = json.loads(match.group(0))
                        if not isinstance(data, list):
                            raise ValueError("Ожидался список контактов.")
                        cleaned = []
                        for item in data:
                            if not isinstance(item, dict):
                                continue
                            name = str(item.get("name") or "").strip()
                            email = str(item.get("email") or "").strip()
                            phone = str(item.get("phone") or "").strip()
                            notes = str(item.get("notes") or "").strip()
                            if not name and email:
                                name = email.split("@", 1)[0]
                            if not name and not email:
                                continue
                            if email and not re.fullmatch(r"[\\w.+-]+@[\\w.-]+\\.[a-zа-я]{2,}", email, re.IGNORECASE):
                                continue
                            cleaned.append({"name": name, "email": email, "phone": phone, "notes": notes})
                        if not cleaned:
                            raise ValueError("Не удалось найти контакты с именем или корректной почтой.")
                        result = (cleaned, None)
                    except Exception as exc:
                        result = (None, str(exc))
                    def finish():
                        parse_button.configure(state="normal")
                        if not dialog.winfo_exists():
                            return
                        contacts, error = result
                        if error:
                            hint.set("Ошибка разбора: " + error)
                            return
                        parsed_contacts[:] = contacts
                        for contact in contacts:
                            preview.insert("", "end", values=(
                                contact["name"], contact["email"], contact["phone"], contact["notes"]
                            ))
                        hint.set(f"Найдено контактов: {len(contacts)}. Проверь данные и нажми «Добавить в адресную книгу».")
                        import_button.configure(state="normal")
                    try:
                        dialog.after(0, finish)
                    except tk.TclError:
                        pass

                threading.Thread(target=worker, daemon=True).start()

            def import_contacts():
                if not parsed_contacts:
                    return
                book = records()
                added = 0
                skipped = 0
                for contact in parsed_contacts:
                    email_key = contact["email"].casefold()
                    name_key = contact["name"].casefold()
                    duplicate = any(
                        (email_key and item.get("email", "").casefold() == email_key)
                        or saved_name.casefold() == name_key
                        for saved_name, item in book.items()
                    )
                    if duplicate:
                        skipped += 1
                        continue
                    name = contact["name"]
                    base_name, suffix = name, 2
                    while name in book:
                        name = f"{base_name} ({suffix})"
                        suffix += 1
                    book[name] = {
                        "phone": contact["phone"],
                        "email": contact["email"],
                        "notes": contact["notes"],
                    }
                    added += 1
                try:
                    save_address_book(book)
                except OSError as exc:
                    messagebox.showerror("Ошибка сохранения", str(exc), parent=dialog)
                    return
                refresh()
                status.set(f"Умный импорт: добавлено {added}, пропущено повторов {skipped}")
                messagebox.showinfo(
                    "Импорт завершён",
                    f"Добавлено контактов: {added}\\nПропущено повторов: {skipped}",
                    parent=dialog,
                )
                dialog.destroy()

            buttons = ttk.Frame(frame)
            buttons.pack(fill="x", pady=(8, 0))
            parse_button = ttk.Button(buttons, text="Разобрать с помощью ИИ", command=parse_with_ai)
            parse_button.pack(side="left")
            import_button = ttk.Button(buttons, text="Добавить в адресную книгу", command=import_contacts, state="disabled")
            import_button.pack(side="left", padx=8)
            ttk.Button(buttons, text="Закрыть", command=dialog.destroy).pack(side="right")
            activate_modal(dialog, root)

        table.bind("<<TreeviewSelect>>", selected)
        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Новый контакт", command=clear_editor).pack(side="left")
        ttk.Button(controls, text="Умный импорт", command=open_smart_import).pack(side="left", padx=(8, 0))
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
