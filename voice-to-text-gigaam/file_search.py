"""Web and local file search UI."""
from __future__ import annotations

import os
import re
import threading
import traceback
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

from file_indexer import refresh_and_search
from notifications import show_notification

def search_web(text: str):
    query = re.sub(r"^\s*найди\s+в\s+интернете\s*", "", text, flags=re.IGNORECASE).strip()
    if not query:
        print("Не распознан поисковый запрос.")
        return
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
    print(f"Открываю поиск в интернете: {query}")

def show_file_results(parent, paths: list[Path], query: str):
    import tkinter as tk
    from tkinter import ttk, messagebox
    root = tk.Toplevel(parent)
    root.title(f"Результаты поиска: {query}")
    root.geometry("850x420")
    root.minsize(550, 260)
    # Окно создаётся после фонового поиска: явно выводим его на передний план,
    # иначе Windows может оставить его позади главного окна/терминала.
    root.attributes("-topmost", True)
    root.update_idletasks()
    root.deiconify()
    root.lift()
    root.focus_force()
    root.after(700, lambda: root.attributes("-topmost", False))
    ttk.Label(root, text=f"Найдено файлов: {len(paths)}. Двойной щелчок — открыть файл.").pack(
        anchor="w", padx=12, pady=(12, 6))
    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True, padx=12, pady=6)
    scrollbar = ttk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")
    listing = tk.Listbox(frame, yscrollcommand=scrollbar.set, font=("Segoe UI", 10))
    listing.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=listing.yview)
    for path in paths:
        listing.insert("end", str(path))
    def open_selected(_event=None):
        selection = listing.curselection()
        if selection:
            try:
                os.startfile(str(paths[selection[0]]))
            except OSError as exc:
                messagebox.showerror("Не удалось открыть файл", str(exc))
    listing.bind("<Double-Button-1>", open_selected)
    ttk.Button(root, text="Открыть выбранный файл", command=open_selected).pack(pady=(0, 12))
    root.transient(parent)
    root.lift()
    root.focus_force()

def search_files(text: str, parent=None):
    # Поддерживаем обе формулировки: «найди файл ...» и «найди ...».
    query = re.sub(r"^\s*найди\s+(?:файл\s+)?", "", text, flags=re.IGNORECASE).strip().strip('"«»')
    # Убираем знаки препинания, которые распознавание речи часто добавляет в конце фразы.
    # Убираем финальную пунктуацию распознавания, включая несколько знаков подряд.
    query = query.rstrip(" \t\r\n.,!?;:…。،؛؟\"'»”’)]}")
    query = query.strip()
    if not query:
        print("Не распознано имя файла. Скажите, например: «найди файл договор».")
        return
    if parent is None:
        print("Поиск файлов требует запущенного главного окна приложения.")
        return
    threading.Thread(target=run_file_search, args=(query, parent), daemon=True, name="file-search").start()

def run_file_search(query: str, parent):
    print(f"Ищу «{query}» по MFT и SQLite. Первое индексирование может занять некоторое время...")
    try:
        matches = refresh_and_search(
            query,
            report=lambda message: print(f"[Поиск файлов] {message}", flush=True),
        )
    except Exception as exc:
        print(f"Ошибка MFT-поиска: {exc}")
        try:
            parent.after(0, lambda: show_notification("Поиск файлов", str(exc)))
        except Exception:
            pass
        return

    if not matches:
        print(f"Файлы по запросу «{query}» не найдены.")
        try:
            parent.after(0, lambda: show_notification("Поиск файлов", f"Файлы «{query}» не найдены."))
        except Exception:
            pass
        return

    print(f"Найдено файлов: {len(matches)}")
    try:
        parent.after(0, lambda: show_file_results(parent, matches, query))
    except Exception as exc:
        print(f"Не удалось открыть окно результатов: {exc}")
        traceback.print_exc()

