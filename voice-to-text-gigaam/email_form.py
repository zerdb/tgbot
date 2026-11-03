"""Desktop email composer with Windows Explorer clipboard file support."""
from __future__ import annotations

import ctypes
import os
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from email_manager import load_address_book, send_email


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


def open_email_form(initial_subject: str = "", parent=None):
    """Open a desktop email composer with explicit contact and manual-address fields."""
    def show():
        if parent is None or not parent.winfo_exists():
            print("Главное окно закрыто: форму почты открыть нельзя.")
            return
        root = tk.Toplevel(parent)
        root.title("GigaAM — отправка почты")
        root.geometry("650x590")
        root.minsize(560, 480)
        root.attributes("-topmost", True)

        outer = ttk.Frame(root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Новое письмо", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 12))

        book_items = list(load_address_book().items())
        contact_names = [name for name, _address in book_items]
        ttk.Label(outer, text="Контакт из адресной книги").pack(anchor="w")
        contact_var = tk.StringVar(master=root)
        recipient = ttk.Combobox(outer, textvariable=contact_var, values=contact_names, state="readonly")
        recipient.pack(fill="x", pady=(3, 8))
        selected_address = {"value": ""}

        def select_contact(_event=None):
            index = recipient.current()
            selected_address["value"] = book_items[index][1].strip() if 0 <= index < len(book_items) else ""

        recipient.bind("<<ComboboxSelected>>", select_contact)

        ttk.Label(outer, text="Или введите email вручную").pack(anchor="w")
        manual_address_var = tk.StringVar(master=root)
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
            # Always derive the automatic subject from the current attachment list.
            # Only file names are used; full directory paths never enter the subject.
            names = [Path(path).name for path in attachment_paths]
            if names:
                subject_var.set(", ".join(names)[:240])
            else:
                subject_var.set(initial_subject.strip())

        def add_paths(paths):
            for item in paths:
                path = str(Path(item))
                if Path(path).is_file() and path not in attachment_paths:
                    attachment_paths.append(path)
                    listbox.insert("end", f"{Path(path).name}  —  {path}")
            update_subject_from_files()
            refresh_count()

        def refresh_count():
            status_var.set(f"Вложений: {len(attachment_paths)}")

        status_var = tk.StringVar(master=root, value="Вложений: 0")
        add_paths(copied_file_paths())
        # Explorer may briefly keep the clipboard open while the voice command
        # launches this window. Retry once after the window has initialized.
        clipboard_attempts = {"count": 0}
        def retry_clipboard_import():
            # Explorer can hold or populate the clipboard slightly after Ctrl+C.
            # Retry several times instead of relying on a single timing window.
            clipboard_attempts["count"] += 1
            add_paths(copied_file_paths())
            if clipboard_attempts["count"] < 12:
                root.after(300, retry_clipboard_import)
        root.after(250, retry_clipboard_import)

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
            address = manual_address or selected_address["value"]
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

            # Build the outgoing subject directly from the exact attachment list.
            # This is the source of truth; it cannot be stale or depend on Tk events.
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

        # Final initialization: after every form widget has been created,
        # fill the subject field with attachment file names only (no paths).
        update_subject_from_files()

        root.bind("<Escape>", lambda _event: root.destroy())
        root.transient(parent)
        root.lift()
        root.focus_force()

    if parent is None:
        print("Для открытия почты требуется главное окно приложения.")
        return
    try:
        parent.after(0, show)
    except tk.TclError:
        print("Не удалось открыть форму почты: главное окно уже закрыто.")
