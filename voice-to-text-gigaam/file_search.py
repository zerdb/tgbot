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

from file_indexer import refresh_and_search, refresh_and_search_folders

_search_requests = queue.Queue()
_search_results = queue.Queue()
_folder_results = queue.Queue()
_polling_parent = None
_busy_callback = None


def search_web(text: str):
    query = re.sub(r"^\s*найди\s+в\s+интернете\s*", "", text, flags=re.IGNORECASE).strip()
    if not query:
        print("Не распознан поисковый запрос.")
        return
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
    print(f"Открываю поиск в интернете: {query}")


def start_file_search_ui(parent, busy_callback=None):
    """Start queue polling on Tk's main thread before mainloop()."""
    global _polling_parent, _busy_callback
    _polling_parent = parent
    _busy_callback = busy_callback
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




_FOLDER_ALIASES = {
    "windowsystem32": lambda: Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32",
    "виндовссистем32": lambda: Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32",
    "system32": lambda: Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32",
    "систем32": lambda: Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32",
    "системтридцатьдва": lambda: Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32",
    "системтридцатьвторой": lambda: Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32",
    "windows": lambda: Path(os.environ.get("WINDIR", r"C:\Windows")),
    "виндовс": lambda: Path(os.environ.get("WINDIR", r"C:\Windows")),
    "загрузки": lambda: Path.home() / "Downloads",
    "downloads": lambda: Path.home() / "Downloads",
    "документы": lambda: Path.home() / "Documents",
    "documents": lambda: Path.home() / "Documents",
    "рабочийстол": lambda: Path.home() / "Desktop",
    "desktop": lambda: Path.home() / "Desktop",
    "изображения": lambda: Path.home() / "Pictures",
    "картинки": lambda: Path.home() / "Pictures",
    "pictures": lambda: Path.home() / "Pictures",
}


def _folder_search_key(value: str) -> str:
    return "".join(char for char in str(value or "").casefold().replace("ё", "е") if char.isalnum())


def open_folder_by_name(text: str, parent=None):
    """Open a known folder immediately or search arbitrary folders via the MFT index."""
    query = str(text or "").strip().strip('"«»').rstrip(" .,!?:;")
    if not query:
        print("Не распознано название папки.")
        return True
    if parent is None:
        print("Открытие папок требует запущенного главного окна приложения.")
        return True

    direct_path = Path(os.path.expandvars(os.path.expanduser(query)))
    if direct_path.is_absolute() and direct_path.is_dir():
        try:
            os.startfile(str(direct_path))
            print(f"Открываю папку: {direct_path}", flush=True)
        except OSError as exc:
            print(f"Не удалось открыть папку: {exc}", flush=True)
        return True

    alias_path = _FOLDER_ALIASES.get(_folder_search_key(query))
    if alias_path:
        candidate = alias_path()
        if candidate.is_dir():
            try:
                os.startfile(str(candidate))
                print(f"Открываю папку: {candidate}", flush=True)
            except OSError as exc:
                print(f"Не удалось открыть папку: {exc}", flush=True)
            return True

    print(f"Ищу папку «{query}» по MFT и SQLite...", flush=True)
    threading.Thread(
        target=_folder_search_worker, args=(query, parent),
        daemon=True, name="folder-search",
    ).start()
    return False


def _folder_search_worker(query: str, parent):
    try:
        matches = refresh_and_search_folders(
            query, report=lambda message: print(f"[Поиск папок] {message}", flush=True)
        )
        _folder_results.put(("success", parent, (query, matches)))
    except Exception as exc:
        _folder_results.put(("error", parent, (query, str(exc))))


def show_folder_results(parent, paths: list[Path], query: str):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from dialog_utils import activate_modal

    window = tk.Toplevel(parent)
    window.title(f"Найденные папки: {query}")
    window.geometry("780x380")
    window.minsize(520, 240)
    window.transient(parent)
    ttk.Label(
        window,
        text=f"Найдено папок: {len(paths)}. Двойной щелчок — открыть выбранную папку.",
    ).pack(anchor="w", padx=12, pady=(12, 6))
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
                window.destroy()
            except OSError as exc:
                messagebox.showerror("Не удалось открыть папку", str(exc), parent=window)

    listing.bind("<Double-Button-1>", open_selected)
    ttk.Button(window, text="Открыть выбранную папку", command=open_selected).pack(pady=(0, 12))
    activate_modal(window, parent)


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
                if _busy_callback:
                    _busy_callback("Ищу файлы…")
                threading.Thread(target=_search_worker, args=(query, parent), daemon=True, name="file-search").start()

        while True:
            try:
                folder_status, folder_parent, folder_payload = _folder_results.get_nowait()
            except queue.Empty:
                break
            if folder_parent is not parent:
                continue
            if _busy_callback:
                _busy_callback(None)
            query, folder_data = folder_payload
            if folder_status == "error":
                from tkinter import messagebox
                messagebox.showerror(
                    "Ошибка поиска папок",
                    f"Не удалось найти папку «{query}»:\\n{folder_data}",
                    parent=parent,
                )
            elif len(folder_data) == 1:
                try:
                    os.startfile(str(folder_data[0]))
                    print(f"Открываю папку: {folder_data[0]}", flush=True)
                except OSError as exc:
                    from tkinter import messagebox
                    messagebox.showerror("Не удалось открыть папку", str(exc), parent=parent)
            elif folder_data:
                show_folder_results(parent, folder_data, query)
            else:
                from tkinter import messagebox
                messagebox.showinfo(
                    "Поиск папок",
                    f"Папка «{query}» не найдена. Проверьте, что MFT-индекс создан и актуален.",
                    parent=parent,
                )

        while True:
            try:
                status, result_parent, payload = _search_results.get_nowait()
            except queue.Empty:
                break
            if result_parent is not parent:
                continue
            if _busy_callback:
                _busy_callback(None)
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
    from dialog_utils import activate_modal

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
    activate_modal(window, parent)
