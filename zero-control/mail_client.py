"""Unified Zero Control mail workspace: inbox, composer and shared contacts."""
from __future__ import annotations

import html
import re
import threading
import tkinter as tk
from email.utils import parseaddr
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

from dialog_utils import center_window, apply_modern_style
from email_manager import load_address_book, save_address_book, send_email


def open_mail_client(parent, initial_tab="inbox", start_new_contact=False,
                     add_files_on_open=False, recipient_name=""):
    """Open one workspace for incoming mail, composing and the shared address book."""
    if parent is None or not parent.winfo_exists():
        return

    win = tk.Toplevel(parent)
    apply_modern_style(win)
    win.title("Zero Control — умная почта")
    win.geometry("1120x760")
    win.minsize(900, 620)
    win.attributes("-topmost", True)

    outer = ttk.Frame(win, padding=14)
    outer.pack(fill="both", expand=True)
    header = ttk.Frame(outer)
    header.pack(fill="x", pady=(0, 10))
    ttk.Label(header, text="✉  Почта", font=("Segoe UI", 19, "bold")).pack(side="left")
    ttk.Label(header, text="Входящие · письма · контакты").pack(side="left", padx=(14, 0), pady=(7, 0))

    notebook = ttk.Notebook(outer)
    notebook.pack(fill="both", expand=True)

    inbox_tab = ttk.Frame(notebook, padding=10)
    compose_tab = ttk.Frame(notebook, padding=14)
    contacts_tab = ttk.Frame(notebook, padding=10)
    notebook.add(inbox_tab, text="📥  Входящие")
    notebook.add(compose_tab, text="✍  Написать")
    notebook.add(contacts_tab, text="👥  Контакты")

    # -------------------- ВХОДЯЩИЕ --------------------
    inbox_toolbar = ttk.Frame(inbox_tab)
    inbox_toolbar.pack(fill="x")
    query = tk.StringVar(master=win)
    search_entry = ttk.Entry(inbox_toolbar, textvariable=query)
    search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
    status = tk.StringVar(master=win, value="Почта ещё не загружена.")
    body = ttk.Panedwindow(inbox_tab, orient="horizontal")
    body.pack(fill="both", expand=True, pady=10)
    left = ttk.Frame(body)
    right = ttk.Frame(body)
    body.add(left, weight=1)
    body.add(right, weight=2)
    listing = ttk.Treeview(left, columns=("from", "subject", "date"), show="headings")
    for col, label, width in (("from", "От кого", 150), ("subject", "Тема", 230), ("date", "Дата", 130)):
        listing.heading(col, text=label)
        listing.column(col, width=width, anchor="w")
    listing.pack(fill="both", expand=True)
    viewer = None
    plain = None
    try:
        from tkinterweb import HtmlFrame
        viewer = HtmlFrame(right, messages_enabled=False)
        viewer.pack(fill="both", expand=True)
        html_supported = True
    except Exception:
        html_supported = False
        plain = tk.Text(right, wrap="word", font=("Segoe UI", 10), state="disabled")
        plain.pack(fill="both", expand=True)
    messages = []

    def render_message(item):
        if html_supported:
            source = item.get("html_body") or (
                "<html><body style='font-family:Segoe UI,Arial;padding:18px;white-space:pre-wrap'>"
                + html.escape(item.get("body", "")) + "</body></html>"
            )
            viewer.load_html(source)
        else:
            plain.configure(state="normal")
            plain.delete("1.0", "end")
            plain.insert("1.0", "HTML-просмотрщик не установлен. Текст письма:\n\n" + item.get("body", ""))
            plain.configure(state="disabled")

    def show_message(_event=None):
        selection = listing.selection()
        if not selection:
            return
        item = messages[int(selection[0])]
        if html_supported:
            head = (
                "<div style='font:14px Segoe UI;padding:10px;background:#f1f3f4'><b>"
                + html.escape(item.get("subject") or "(без темы)") + "</b><br>От: "
                + html.escape(item.get("from_name") or "") + " &lt;"
                + html.escape(item.get("from_email") or "") + "&gt;<br>"
                + html.escape(item.get("date") or "") + "</div>"
            )
            source = item.get("html_body") or (
                "<html><body style='font-family:Segoe UI;padding:18px;white-space:pre-wrap'>"
                + html.escape(item.get("body", "")) + "</body></html>"
            )
            viewer.load_html(head + source.replace("<body", "<body style='font-family:Segoe UI;padding:18px'"))
        else:
            render_message(item)

    listing.bind("<<TreeviewSelect>>", show_message)
    loading = {"window": None}

    def load_inbox():
        status.set("Подключаюсь к почте…")
        refresh_button.configure(state="disabled")
        overlay = tk.Toplevel(win)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.configure(bg="#202124")
        tk.Label(overlay, text="⏳  Загружаю почту…", bg="#202124", fg="white",
                 font=("Segoe UI", 10, "bold"), padx=16, pady=10).pack()
        overlay.update_idletasks()
        overlay.geometry(f"+{win.winfo_screenwidth()-overlay.winfo_reqwidth()-24}+{win.winfo_screenheight()//2}")
        loading["window"] = overlay
        search_text = query.get().strip()

        def worker():
            try:
                from mail_reader import fetch_messages
                result, error = fetch_messages(limit=100, query=search_text), None
            except Exception as exc:
                result, error = [], str(exc)

            def finish():
                if not win.winfo_exists():
                    return
                messages[:] = result
                listing.delete(*listing.get_children())
                if html_supported:
                    viewer.load_html("<html><body style='font-family:Segoe UI;padding:24px'>Выбери письмо слева.</body></html>")
                else:
                    plain.configure(state="normal")
                    plain.delete("1.0", "end")
                    plain.configure(state="disabled")
                if error:
                    status.set("Ошибка загрузки: " + error)
                else:
                    for index, item in enumerate(messages):
                        listing.insert("", "end", iid=str(index), values=(
                            item.get("from_name") or item.get("from_email"),
                            item.get("subject"), item.get("date")
                        ))
                    status.set(f"Загружено писем: {len(messages)}")
                    if messages:
                        first = listing.get_children()[0]
                        listing.selection_set(first)
                        listing.focus(first)
                        show_message()
                refresh_button.configure(state="normal")
                try:
                    overlay.destroy()
                except tk.TclError:
                    pass
                loading["window"] = None

            try:
                win.after(0, finish)
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True, name="mail-inbox-load").start()

    refresh_button = ttk.Button(inbox_toolbar, text="↻  Обновить", command=load_inbox)
    refresh_button.pack(side="left")
    search_entry.bind("<Return>", lambda _event: load_inbox())
    ttk.Label(inbox_tab, textvariable=status).pack(anchor="w", pady=(2, 0))

    # -------------------- НАПИСАТЬ ПИСЬМО --------------------
    ttk.Label(compose_tab, text="Новое письмо", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 12))
    book_cache = load_address_book()
    recipient_var = tk.StringVar(master=win)
    contact_values = [name for name, item in book_cache.items() if item.get("email")]
    ttk.Label(compose_tab, text="Получатель из адресной книги").pack(anchor="w")
    recipient_box = ttk.Combobox(compose_tab, textvariable=recipient_var, values=contact_values, state="readonly")
    recipient_box.pack(fill="x", pady=(3, 8))
    address_var = tk.StringVar(master=win)
    ttk.Label(compose_tab, text="Кому (можно ввести адрес вручную)").pack(anchor="w")
    ttk.Entry(compose_tab, textvariable=address_var).pack(fill="x", pady=(3, 9))

    def choose_recipient(_event=None):
        name = recipient_var.get()
        address_var.set(f"{name} <{book_cache.get(name, {}).get('email', '')}>")

    recipient_box.bind("<<ComboboxSelected>>", choose_recipient)
    ttk.Label(compose_tab, text="Тема").pack(anchor="w")
    subject_var = tk.StringVar(master=win)
    ttk.Entry(compose_tab, textvariable=subject_var).pack(fill="x", pady=(3, 9))
    ttk.Label(compose_tab, text="Текст письма").pack(anchor="w")
    message_body = tk.Text(compose_tab, height=7, wrap="word", font=("Segoe UI", 10))
    message_body.pack(fill="x", pady=(3, 9))
    attach_frame = ttk.LabelFrame(compose_tab, text="Вложения", padding=8)
    attach_frame.pack(fill="both", expand=True)
    attach_list = tk.Listbox(attach_frame, height=5, selectmode=tk.EXTENDED)
    attach_list.pack(side="left", fill="both", expand=True)
    attach_scroll = ttk.Scrollbar(attach_frame, orient="vertical", command=attach_list.yview)
    attach_scroll.pack(side="right", fill="y")
    attach_list.configure(yscrollcommand=attach_scroll.set)
    attachment_paths = []

    def add_attachment_paths(paths):
        for value in paths:
            path = str(Path(value))
            if Path(path).is_file() and path not in attachment_paths:
                attachment_paths.append(path)
                attach_list.insert("end", f"{Path(path).name} — {path}")
        compose_status.set(f"Вложений: {len(attachment_paths)}")

    def add_files():
        add_attachment_paths(filedialog.askopenfilenames(parent=win, title="Выберите файлы"))

    def remove_files():
        for index in reversed(attach_list.curselection()):
            attach_list.delete(index)
            attachment_paths.pop(index)
        compose_status.set(f"Вложений: {len(attachment_paths)}")

    attach_controls = ttk.Frame(compose_tab)
    attach_controls.pack(fill="x", pady=(7, 0))
    ttk.Button(attach_controls, text="＋  Добавить файлы", command=add_files).pack(side="left")
    ttk.Button(attach_controls, text="Убрать выбранные", command=remove_files).pack(side="left", padx=8)
    compose_status = tk.StringVar(master=win, value="Вложений: 0")
    ttk.Label(attach_controls, textvariable=compose_status).pack(side="right")

    def send_current_email():
        target = parseaddr(address_var.get().strip())[1].strip() or address_var.get().strip()
        if not target:
            messagebox.showwarning("Нет получателя", "Выбери контакт или введи адрес почты.", parent=win)
            recipient_box.focus_set()
            return
        if not attachment_paths and not messagebox.askyesno("Без вложений", "Отправить письмо без файлов?", parent=win):
            return
        subject = subject_var.get().strip() or "Без темы"
        body_text = message_body.get("1.0", "end-1c")
        paths = list(attachment_paths)
        send_button.configure(state="disabled")
        compose_status.set("Отправляю письмо…")

        def worker():
            try:
                send_email(target, subject, body_text, paths)
                result = None
            except Exception as exc:
                result = str(exc)

            def finish():
                if not win.winfo_exists():
                    return
                send_button.configure(state="normal")
                if result:
                    compose_status.set("Ошибка отправки")
                    messagebox.showerror("Не удалось отправить", result, parent=win)
                else:
                    compose_status.set("Письмо отправлено")
                    messagebox.showinfo("Готово", f"Письмо отправлено на {target}.", parent=win)
                    subject_var.set("")
                    message_body.delete("1.0", "end")
                    recipient_var.set("")
                    address_var.set("")
                    attachment_paths.clear()
                    attach_list.delete(0, "end")
                    compose_status.set("Письмо отправлено · Вложений: 0")

            try:
                win.after(0, finish)
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True, name="mail-sender").start()

    compose_buttons = ttk.Frame(compose_tab)
    compose_buttons.pack(fill="x", pady=(9, 0))
    send_button = ttk.Button(compose_buttons, text="➤  Отправить", command=send_current_email)
    send_button.pack(side="right")

    # -------------------- КОНТАКТЫ --------------------
    ttk.Label(contacts_tab, text="Общая адресная книга", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    ttk.Label(contacts_tab, text="Эти контакты используются при создании писем и голосовой отправке файлов.").pack(anchor="w", pady=(2, 9))
    contact_columns = ("name", "phone", "email", "notes")
    contact_table = ttk.Treeview(contacts_tab, columns=contact_columns, show="headings", selectmode="browse")
    for key, label, width in (
        ("name", "Имя", 190), ("phone", "Телефон", 145),
        ("email", "Электронная почта", 260), ("notes", "Заметка", 220)
    ):
        contact_table.heading(key, text=label)
        contact_table.column(key, width=width, anchor="w")
    contact_table.pack(fill="both", expand=True)
    editor = ttk.LabelFrame(contacts_tab, text="Карточка контакта", padding=10)
    editor.pack(fill="x", pady=(9, 7))
    contact_vars = {key: tk.StringVar(master=win) for key in contact_columns}
    for index, (key, label) in enumerate((("name", "Имя"), ("phone", "Телефон"), ("email", "Почта"), ("notes", "Заметка"))):
        ttk.Label(editor, text=label).grid(row=0, column=index, sticky="w", padx=(0, 8))
        ttk.Entry(editor, textvariable=contact_vars[key], width=25).grid(row=1, column=index, sticky="ew", padx=(0, 8))
        editor.columnconfigure(index, weight=1)
    contacts_status = tk.StringVar(master=win)
    ttk.Label(contacts_tab, textvariable=contacts_status).pack(anchor="w")

    def refresh_contacts(select_name=None):
        current = load_address_book()
        book_cache.clear()
        book_cache.update(current)
        contact_values = [name for name, item in current.items() if item.get("email")]
        recipient_box.configure(values=contact_values)
        contact_table.delete(*contact_table.get_children())
        for name, item in sorted(current.items(), key=lambda pair: pair[0].casefold()):
            contact_table.insert("", "end", iid=name, values=(
                name, item.get("phone", ""), item.get("email", ""), item.get("notes", "")
            ))
        contacts_status.set(f"Контактов: {len(current)}")
        if select_name and contact_table.exists(select_name):
            contact_table.selection_set(select_name)
            contact_table.focus(select_name)
            contact_table.see(select_name)

    def clear_contact():
        for variable in contact_vars.values():
            variable.set("")
        contact_table.selection_remove(contact_table.selection())

    def select_contact(_event=None):
        selection = contact_table.selection()
        if not selection:
            return
        name = selection[0]
        item = book_cache.get(name, {})
        contact_vars["name"].set(name)
        for key in ("phone", "email", "notes"):
            contact_vars[key].set(item.get(key, ""))

    def save_contact():
        name = contact_vars["name"].get().strip()
        email = contact_vars["email"].get().strip()
        if not name:
            messagebox.showwarning("Нет имени", "Укажи имя контакта.", parent=win)
            return
        if email and not re.fullmatch(r"[\\w.+-]+@[\\w.-]+\\.[a-zа-я]{2,}", email, re.IGNORECASE):
            messagebox.showwarning("Неверная почта", "Проверь адрес электронной почты.", parent=win)
            return
        book = load_address_book()
        selected = contact_table.selection()
        old_name = selected[0] if selected else None
        if old_name and old_name != name:
            book.pop(old_name, None)
        book[name] = {
            "phone": contact_vars["phone"].get().strip(),
            "email": email,
            "notes": contact_vars["notes"].get().strip(),
        }
        try:
            save_address_book(book)
        except OSError as exc:
            messagebox.showerror("Ошибка сохранения", str(exc), parent=win)
            return
        refresh_contacts(name)
        contacts_status.set(f"Контакт «{name}» сохранён")

    def delete_contact():
        selection = contact_table.selection()
        if not selection:
            messagebox.showinfo("Контакт не выбран", "Выбери контакт в таблице.", parent=win)
            return
        name = selection[0]
        if not messagebox.askyesno("Удалить контакт", f"Удалить «{name}»?", parent=win):
            return
        book = load_address_book()
        book.pop(name, None)
        try:
            save_address_book(book)
        except OSError as exc:
            messagebox.showerror("Ошибка сохранения", str(exc), parent=win)
            return
        clear_contact()
        refresh_contacts()
        contacts_status.set(f"Контакт «{name}» удалён")

    def write_to_contact():
        email = contact_vars["email"].get().strip()
        name = contact_vars["name"].get().strip()
        if not email:
            messagebox.showinfo("Нет почты", "У этого контакта не указан email.", parent=win)
            return
        recipient_var.set(name)
        address_var.set(f"{name} <{email}>")
        notebook.select(compose_tab)
        subject_var.set("")
        message_body.focus_set()

    contact_table.bind("<<TreeviewSelect>>", select_contact)
    contact_buttons = ttk.Frame(contacts_tab)
    contact_buttons.pack(fill="x", pady=(7, 0))
    ttk.Button(contact_buttons, text="＋  Новый контакт", command=clear_contact).pack(side="left")
    ttk.Button(contact_buttons, text="Сохранить", command=save_contact).pack(side="left", padx=7)
    ttk.Button(contact_buttons, text="Удалить", command=delete_contact).pack(side="left")
    ttk.Button(contact_buttons, text="✉  Написать письмо", command=write_to_contact).pack(side="left", padx=7)

    # Навигация верхними кнопками с иконками.
    nav = ttk.Frame(outer)
    nav.pack(fill="x", pady=(10, 0))
    ttk.Button(nav, text="📥  Входящие", command=lambda: notebook.select(inbox_tab)).pack(side="left", padx=(0, 6))
    ttk.Button(nav, text="✍  Новое письмо", command=lambda: notebook.select(compose_tab)).pack(side="left", padx=6)
    ttk.Button(nav, text="👥  Контакты", command=lambda: notebook.select(contacts_tab)).pack(side="left", padx=6)
    ttk.Label(nav, text="Контакты общие для писем и голосовых команд.").pack(side="right")

    def normalized_tokens(value):
        value = re.sub(r"[^а-яa-z0-9 ]", " ", str(value or "").lower().replace("ё", "е"))
        return {
            re.sub(r"(иями|ями|ами|ого|ему|ому|ыми|ими|иях|а|я|у|ю|е|ы|и|ом|ем|ь|ъ)$", "", token)
            for token in value.split()
        } - {""}

    def prepare_compose():
        refresh_contacts()
        if recipient_name:
            spoken = normalized_tokens(recipient_name)
            matches = [
                name for name, item in book_cache.items()
                if item.get("email") and spoken and spoken.issubset(normalized_tokens(name))
            ]
            if len(matches) == 1:
                recipient_var.set(matches[0])
                address_var.set(f"{matches[0]} <{book_cache[matches[0]]['email']}>")
            elif len(matches) > 1:
                contacts_status.set("Имя неоднозначно — выбери получателя вручную на вкладке «Написать».")
        if add_files_on_open:
            try:
                from email_form import copied_file_paths
                add_attachment_paths(copied_file_paths())
            except Exception as exc:
                compose_status.set("Не удалось прочитать буфер обмена: " + str(exc))
        notebook.select(compose_tab)

    refresh_contacts()
    if start_new_contact:
        clear_contact()
    if initial_tab == "contacts":
        notebook.select(contacts_tab)
        if start_new_contact:
            contact_vars["name"].set("")
    elif initial_tab == "compose" or add_files_on_open or recipient_name:
        prepare_compose()
    else:
        notebook.select(inbox_tab)
        load_inbox()

    center_window(win, parent)
    win.bind("<Escape>", lambda _event: win.destroy())
