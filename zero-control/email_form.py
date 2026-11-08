"""Desktop email composer with Windows Explorer clipboard file support."""
from __future__ import annotations

import ctypes
import os
import re
import threading
from email.utils import parseaddr
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from email_manager import load_address_book, send_email
from dialog_utils import activate_modal, apply_modern_style


def copied_file_paths() -> list[str]:
    """Read CF_HDROP (files copied in Explorer with Ctrl+C) without extra packages."""
    if os.name != "nt":
        return []
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT
    CF_HDROP = 15
    if not user32.OpenClipboard(None):
        return []
    try:
        handle = user32.GetClipboardData(CF_HDROP)
        if not handle:
            return []
        count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        paths = []
        for index in range(count):
            length = shell32.DragQueryFileW(handle, index, None, 0)
            buffer = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(handle, index, buffer, length + 1)
            path = buffer.value
            if path and Path(path).is_file():
                paths.append(path)
        return paths
    except Exception as exc:
        print(f"Не удалось прочитать скопированные файлы: {exc}")
        return []
    finally:
        user32.CloseClipboard()


def open_email_form(initial_subject: str = "", parent=None, add_files_on_open: bool = False, recipient_name: str = ""):
    """Open the composer; snapshot copied Explorer files before creating any GUI windows."""
    # Read CF_HDROP immediately when the command is received, before Tk schedules
    # the window. Keep this snapshot even if another UI action changes the clipboard.
    clipboard_snapshot = copied_file_paths()

    def show():
        if parent is None or not parent.winfo_exists():
            print("Главное окно закрыто: форму почты открыть нельзя.")
            return
        root = tk.Toplevel(parent)
        apply_modern_style(root)
        root.title("Zero Control — отправка почты")
        root.geometry("650x590")
        root.minsize(560, 480)
        root.attributes("-topmost", True)

        outer = ttk.Frame(root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Новое письмо", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 12))

        book_items = [(name, item.get("email", "")) for name, item in load_address_book().items() if item.get("email")]
        contact_names = [name for name, _address in book_items]
        ttk.Label(outer, text="Контакт из адресной книги").pack(anchor="w")
        contact_var = tk.StringVar(master=root)
        recipient = ttk.Combobox(outer, textvariable=contact_var, values=contact_names, state="readonly")
        recipient.pack(fill="x", pady=(3, 8))
        selected_address = {"value": ""}
        manual_address_var = tk.StringVar(master=root)

        def select_contact(_event=None):
            index = recipient.current()
            if 0 <= index < len(book_items):
                contact_name, contact_email = book_items[index]
                selected_address["value"] = contact_email.strip()
                manual_address_var.set(f"{contact_name} <{selected_address['value']}>")
            else:
                selected_address["value"] = ""
                manual_address_var.set("")

        recipient.bind("<<ComboboxSelected>>", select_contact)

        # Имя получателя извлечено ИИ из голосовой команды. Сопоставляем его
        # с фамилией/именем в адресной книге, учитывая русские падежные окончания.
        def name_key(value):
            value = re.sub(r"[^а-яa-z0-9 ]", " ", str(value or "").lower().replace("ё", "е"))
            tokens = []
            for token in value.split():
                token = re.sub(r"(иями|ями|ами|ого|ему|ому|ыми|ими|иях|иях|а|я|у|ю|е|ы|и|ом|ем|ь|ъ)$", "", token)
                if token:
                    tokens.append(token)
            return tokens

        print(
            f"[Почта] Поиск адресата {recipient_name!r}; контактов с email: {len(book_items)}",
            flush=True,
        )
        if recipient_name:
            spoken_tokens = set(name_key(recipient_name))
            matches = []
            for index, (saved_name, _address) in enumerate(book_items):
                saved_tokens = set(name_key(saved_name))
                # Совпадение по нормализованному имени/фамилии; учитываем
                # склонение и составные записи вроде «Шамиль Мазяров».
                if spoken_tokens and spoken_tokens.issubset(saved_tokens):
                    matches.append(index)
            if not matches:
                for index, (saved_name, _address) in enumerate(book_items):
                    saved_tokens = set(name_key(saved_name))
                    if spoken_tokens and spoken_tokens.intersection(saved_tokens):
                        matches.append(index)
            if len(matches) == 1:
                recipient.current(matches[0])
                select_contact()
                print(f"[Почта] Выбран контакт: {book_items[matches[0]][0]} <{selected_address['value']}>", flush=True)
            elif len(matches) > 1:
                names = ", ".join(book_items[index][0] for index in matches)
                print(f"[Почта] Имя «{recipient_name}» неоднозначно: {names}. Выбери контакт вручную.", flush=True)
            else:
                print(
                    f"[Почта] Контакт «{recipient_name}» не найден среди контактов с email. "
                    "Проверь написание имени и наличие почты в карточке.",
                    flush=True,
                )
        else:
            print("[Почта] Имя адресата не передано из распознавателя команды.", flush=True)

        ttk.Label(outer, text="Кому").pack(anchor="w")
        ttk.Entry(outer, textvariable=manual_address_var).pack(fill="x", pady=(3, 10))

        ttk.Label(outer, text="Тема").pack(anchor="w")
        subject_var = tk.StringVar(master=root, value=initial_subject.strip())
        ttk.Entry(outer, textvariable=subject_var).pack(fill="x", pady=(3, 10))

        ttk.Label(outer, text="Текст письма").pack(anchor="w")
        body = tk.Text(outer, height=5, wrap="word", font=("Segoe UI", 10))
        body.pack(fill="x", pady=(3, 10))

        files_frame = ttk.LabelFrame(outer, text="Вложения", padding=8)
        files_frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(files_frame, height=8, selectmode=tk.EXTENDED)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(files_frame, orient="vertical", command=listbox.yview)
        scrollbar.pack(side="right", fill="y")
        listbox.configure(yscrollcommand=scrollbar.set)
        attachment_paths: list[str] = []

        def update_subject_from_files():
            names = [Path(path).name for path in attachment_paths]
            subject_var.set(", ".join(names)[:240] if names else initial_subject.strip())

        def refresh_count():
            status_var.set(f"Вложений: {len(attachment_paths)}")

        def add_paths(paths):
            for item in paths:
                path = str(Path(item))
                if Path(path).is_file() and path not in attachment_paths:
                    attachment_paths.append(path)
                    listbox.insert("end", f"{Path(path).name}  —  {path}")
            update_subject_from_files()
            refresh_count()

        status_var = tk.StringVar(master=root, value="Вложений: 0")
        # Attach the command-time clipboard snapshot first. Never open the file picker automatically.
        add_paths(clipboard_snapshot)
        clipboard_attempts = {"count": 0}

        def retry_clipboard_import():
            clipboard_attempts["count"] += 1
            add_paths(copied_file_paths())
            if clipboard_attempts["count"] < 20:
                root.after(300, retry_clipboard_import)

        root.after(100, retry_clipboard_import)

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(8, 0))

        def add_files():
            selected = filedialog.askopenfilenames(parent=root, title="Выберите файлы")
            add_paths(selected)

        def remove_files():
            selected = list(listbox.curselection())
            for index in reversed(selected):
                listbox.delete(index)
                attachment_paths.pop(index)
            update_subject_from_files()
            refresh_count()

        ttk.Button(controls, text="Добавить файлы…", command=add_files).pack(side="left")
        ttk.Button(controls, text="Убрать выбранные", command=remove_files).pack(side="left", padx=8)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Label(buttons, textvariable=status_var).pack(side="left")

        def send():
            manual_address = manual_address_var.get().strip()
            # В поле «Кому» показываем имя и адрес, но SMTP получает только email.
            address = parseaddr(manual_address)[1].strip() or selected_address["value"]
            if not address:
                messagebox.showwarning(
                    "Нет получателя",
                    "Выберите имя в поле «Контакт из адресной книги» или введите email вручную.",
                    parent=root,
                )
                recipient.focus_set()
                return
            if not attachment_paths and not messagebox.askyesno(
                "Без вложений", "Отправить письмо без файлов?", parent=root
            ):
                return

            if attachment_paths:
                subject = ", ".join(Path(path).name for path in attachment_paths)[:240]
                subject_var.set(subject)
            else:
                subject = subject_var.get().strip() or "Файлы"
            content = body.get("1.0", "end-1c")
            paths = list(attachment_paths)
            send_button.configure(state="disabled")
            cancel_button.configure(state="disabled")
            status_var.set("Отправляю письмо…")

            def worker():
                try:
                    send_email(address, subject, content, paths)
                    def sent():
                        messagebox.showinfo("Готово", "Письмо успешно отправлено.", parent=root)
                        root.destroy()
                    root.after(0, sent)
                except Exception as exc:
                    error_text = str(exc)
                    def failed():
                        send_button.configure(state="normal")
                        cancel_button.configure(state="normal")
                        status_var.set("Не удалось отправить письмо")
                        messagebox.showerror("Ошибка отправки", error_text, parent=root)
                    root.after(0, failed)

            threading.Thread(target=worker, daemon=True, name="email-sender").start()

        send_button = ttk.Button(buttons, text="Отправить", command=send)
        send_button.pack(side="right")
        cancel_button = ttk.Button(buttons, text="Отмена", command=root.destroy)
        cancel_button.pack(side="right", padx=(0, 8))
        update_subject_from_files()
        root.bind("<Escape>", lambda _event: root.destroy())
        activate_modal(root, parent)

    if parent is None:
        print("Для открытия почты требуется главное окно приложения.")
        return
    try:
        parent.after(0, show)
    except tk.TclError:
        print("Не удалось открыть форму почты: главное окно уже закрыто.")
