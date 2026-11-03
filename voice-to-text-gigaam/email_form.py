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


def open_email_form(initial_subject: str = ""):
    """Open the email form in its own Tk thread."""
    def show():
        root = tk.Tk()
        root.title("GigaAM — отправка почты")
        root.geometry("650x590")
        root.minsize(560, 480)
        root.attributes("-topmost", True)

        outer = ttk.Frame(root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Новое письмо", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 12))

        book = load_address_book()
        contacts = [f"{name} <{address}>" for name, address in book.items()]
        ttk.Label(outer, text="Получатель").pack(anchor="w")
        recipient_var = tk.StringVar()
        contact_addresses = {f"{name} <{address}>": address for name, address in book.items()}
        recipient = ttk.Combobox(outer, textvariable=recipient_var, values=contacts, state="normal")
        recipient.pack(fill="x", pady=(3, 10))
        def select_contact(_event=None):
            selected = recipient_var.get().strip()
            if selected in contact_addresses:
                recipient_var.set(contact_addresses[selected])
        recipient.bind("<<ComboboxSelected>>", select_contact)

        ttk.Label(outer, text="Тема").pack(anchor="w")
        subject_var = tk.StringVar(value=initial_subject or "Файлы")
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
            if initial_subject.strip():
                return
            names = [Path(path).name for path in attachment_paths]
            if names:
                subject_var.set(", ".join(names)[:240])
            else:
                subject_var.set("Файлы")

        def add_paths(paths):
            for item in paths:
                path = str(Path(item))
                if Path(path).is_file() and path not in attachment_paths:
                    attachment_paths.append(path)
                    listbox.insert("end", f"{Path(path).name}  —  {path}")
            update_subject_from_files()

        add_paths(copied_file_paths())

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
        ttk.Button(controls, text="Добавить файлы…", command=add_files).pack(side="left")
        ttk.Button(controls, text="Убрать выбранные", command=remove_files).pack(side="left", padx=8)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(14, 0))
        status_var = tk.StringVar(value=f"Вложений: {len(attachment_paths)}")
        ttk.Label(buttons, textvariable=status_var).pack(side="left")
        def refresh_count():
            status_var.set(f"Вложений: {len(attachment_paths)}")
        def send():
            address = recipient_var.get().strip()
            if address in contact_addresses:
                address = contact_addresses[address]
            elif "<" in address and ">" in address:
                address = address.rsplit("<", 1)[1].split(">", 1)[0].strip()
            if not address:
                messagebox.showwarning("Нет получателя", "Выберите контакт или введите email.", parent=root)
                recipient.focus_set()
                return
            if not attachment_paths and not messagebox.askyesno("Без вложений", "Отправить письмо без файлов?", parent=root):
                return
            subject = subject_var.get().strip() or "Файлы"
            content = body.get("1.0", "end-1c")
            paths = list(attachment_paths)
            send_button.configure(state="disabled")
            cancel_button.configure(state="disabled")
            status_var.set("Отправляю письмо…")
            def worker():
                try:
                    send_email(address, subject, content, paths)
                    root.after(0, lambda: (messagebox.showinfo("Готово", "Письмо успешно отправлено.", parent=root), root.destroy()))
                except Exception as exc:
                    def failed():
                        send_button.configure(state="normal")
                        cancel_button.configure(state="normal")
                        status_var.set("Не удалось отправить письмо")
                        messagebox.showerror("Ошибка отправки", error_text, parent=root)
                    error_text = str(exc)
                    root.after(0, failed)
            threading.Thread(target=worker, daemon=True, name="email-sender").start()

        send_button = ttk.Button(buttons, text="Отправить", command=send)
        send_button.pack(side="right")
        cancel_button = ttk.Button(buttons, text="Отмена", command=root.destroy)
        cancel_button.pack(side="right", padx=(0, 8))
        def on_selection(_event=None):
            refresh_count()
        listbox.bind("<<ListboxSelect>>", on_selection)
        root.bind("<Escape>", lambda _event: root.destroy())
        root.mainloop()

    threading.Thread(target=show, daemon=True, name="email-form").start()
