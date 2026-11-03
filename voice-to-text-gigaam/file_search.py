"""Thread-safe local file search and result window."""
from __future__ import annotations

import os
import queue
import re
import threading
import traceback
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

from file_indexer import refresh_and_search

_search_requests = queue.Queue()
_search_results = queue.Queue()
_polling_parent = None


def search_web(text: str):
    query = re.sub(r"^\s*найди\s+в\s+интернете\s*", "", text, flags=re.IGNORECASE).strip()
    if not query:
        print("Не распознан поисковый запрос.")
        return
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
    print(f"Открываю поиск в интернете: {query}")


def start_file_search_ui(parent):
    """Start queue polling on Tk's main thread before mainloop()."""
    global _polling_parent
    _polling_parent = parent
    parent.after(100, _poll_search_queues)


def search_files(text: str, parent=None):
    # May be called from the speech-recognition worker: never touch Tk here.
    query = re.sub(r"^\s*найди\s+(?:файл\s+)?", "", text, flags=re.IGNORECASE).strip().strip('"«»')
    query = query.rstrip(" \t\r\n.,!?;:…。،؛؟").strip()
    if not query:
        print("Не распознано имя файла. Скажите, например: «найди файл договор».")
        return
    if parent is None:
        print("Поиск файлов требует запущенного главного окна приложения.")
        return
    print(f"Запрос на поиск файла: «{query}»", flush=True)
    _search_requests.put((query, parent))


def _search_worker(query: str, parent):
    print(f"Ищу «{query}» по MFT и SQLite. Первое индексирование может занять некоторое время...", flush=True)
    try:
        matches = refresh_and_search(query, report=lambda message: print(f"[Поиск файлов] {message}", flush=True))
        _search_results.put(("success", parent, (query, matches)))
    except Exception as exc:
        error_text = str(exc)
        print(f"Ошибка MFT-поиска: {error_text}", flush=True)
        traceback.print_exc()
        _search_results.put(("error", parent, (query, error_text)))


def _poll_search_queues():
    """All Tk operations happen here, on the main thread."""
    global _polling_parent
    parent = _polling_parent
    if parent is None:
        return
    try:
        if not parent.winfo_exists():
            _polling_parent = None
            return
        while True:
            try:
                query, request_parent = _search_requests.get_nowait()
            except queue.Empty:
                break
            if request_parent is parent:
                threading.Thread(target=_search_worker, args=(query, parent), daemon=True, name="file-search").start()

        while True:
            try:
                status, result_parent, payload = _search_results.get_nowait()
            except queue.Empty:
                break
            if result_parent is not parent:
                continue
            if status == "error":
                query, error_text = payload
                from tkinter import messagebox
                messagebox.showerror("Ошибка поиска файлов", f"Не удалось выполнить поиск «{query}»:\n{error_text}", parent=parent)
            else:
                query, matches = payload
                if matches:
                    print(f"Найдено файлов: {len(matches)}", flush=True)
                    show_file_results(parent, matches, query)
                else:
                    print(f"Файлы по запросу «{query}» не найдены.", flush=True)
                    from tkinter import messagebox
                    messagebox.showinfo("Поиск файлов", f"По запросу «{query}» ничего не найдено.", parent=parent)
        parent.after(100, _poll_search_queues)
    except Exception as exc:
        print(f"Ошибка интерфейса поиска: {exc}", flush=True)
        traceback.print_exc()
        try:
            parent.after(250, _poll_search_queues)
        except Exception:
            _polling_parent = None


def show_file_results(parent, paths: list[Path], query: str):
    import tkinter as tk
    from tkinter import ttk, messagebox

    window = tk.Toplevel(parent)
    window.title(f"Результаты поиска: {query}")
    window.geometry("850x420")
    window.minsize(550, 260)
    window.transient(parent)
    ttk.Label(window, text=f"Найдено файлов: {len(paths)}. Двойной щелчок — открыть файл.").pack(anchor="w", padx=12, pady=(12, 6))
    frame = ttk.Frame(window)
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
                messagebox.showerror("Не удалось открыть файл", str(exc), parent=window)

    listing.bind("<Double-Button-1>", open_selected)
    ttk.Button(window, text="Открыть выбранный файл", command=open_selected).pack(pady=(0, 12))
    window.lift()
    window.focus_force()
