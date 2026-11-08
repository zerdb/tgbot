"""MFT-backed file search window."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox
from urllib.parse import quote_plus

from file_search import search_files
from dialog_utils import center_window, apply_modern_style


def open_workspace(parent):
    win = tk.Toplevel(parent)
    apply_modern_style(win)
    win.title("Zero Control — файлы")
    win.geometry("760x440")
    win.minsize(620, 360)

    frame = ttk.Frame(win, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="⌕  Поиск файлов по MFT", font=("Segoe UI", 17, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Поиск выполняется по Master File Table (MFT) дисков NTFS. "
             "Для работы обязательно запусти PyCharm от имени администратора.",
        wraplength=700,
    ).pack(anchor="w", pady=(6, 14))

    ttk.Label(frame, text="Имя файла или фрагмент имени").pack(anchor="w")
    query = tk.StringVar(master=win)
    entry = ttk.Entry(frame, textvariable=query)
    entry.pack(fill="x", pady=(4, 10))

    status = tk.StringVar(master=win, value="Введи запрос и нажми «Найти через MFT».")
    ttk.Label(frame, textvariable=status, wraplength=700).pack(anchor="w", pady=(0, 12))

    def run_search():
        term = query.get().strip()
        if not term:
            messagebox.showwarning("Поиск по MFT", "Введи имя или часть имени файла.", parent=win)
            return
        status.set("Запрос передан MFT-поиску. Индексирование дисков может занять время.")
        search_files("найди файл " + term, parent)

    ttk.Button(frame, text="🔎  Найти через MFT", command=run_search).pack(anchor="w")
    ttk.Button(
        frame,
        text="🌐  Поиск в интернете",
        command=lambda: webbrowser.open("https://www.google.com/search?q=" + quote_plus(query.get().strip()))
        if query.get().strip() else None,
    ).pack(anchor="w", pady=(8, 0))
    entry.bind("<Return>", lambda _event: run_search())
    center_window(win, parent)
