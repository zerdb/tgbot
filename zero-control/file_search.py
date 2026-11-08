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


def _parse_search_request(raw_query: str) -> dict:
    """Turn natural-language file-search modifiers into local filesystem filters."""
    from datetime import datetime, timedelta

    text = str(raw_query or "").casefold().replace("ё", "е").strip()
    now = datetime.now()
    filters = {"extensions": None, "min_size": None, "max_size": None, "exact_size": None,
               "start": None, "end": None, "date_field": "mtime",
               "drive": None, "folder": None, "sort": None}
    if re.search(r"\b(?:последние|новые|недавние)\s+(?:документ\w*|файл\w*)\b", text):
        filters["sort"] = "date_desc"
    elif re.search(r"\b(?:старые|самые\s+старые)\s+(?:документ\w*|файл\w*)\b", text):
        filters["sort"] = "date_asc"
    ext_groups = [
        (r"\b(?:таблиц\w*\s+excel|excel|эксель)\b", {".xls", ".xlsx"}),
        (r"\bдокумент\w*\b", {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt"}),
        (r"\b(?:документ\w*\s+word|word|ворд)\b", {".doc", ".docx"}),
        (r"\b(?:презентаци\w*)\b", {".ppt", ".pptx"}),
        (r"\b(?:фотографи\w*\s+jpg|картинк\w*\s+jpg|jpg|jpeg)\b", {".jpg", ".jpeg"}),
        (r"\b(?:картинк\w*\s+png|png)\b", {".png"}),
        (r"\b(?:фотографи\w*|фото|изображени\w*|картинк\w*)\b", {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}),
        (r"\b(?:архив\w*|zip)\b", {".zip", ".rar", ".7z"}),
        (r"\b(?:видео|ролик\w*)\b", {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"}),
        (r"\b(?:музык\w*|аудио|песн\w*)\b", {".mp3", ".wav", ".flac", ".m4a", ".aac"}),
        (r"\bpdf\b", {".pdf"}),
        (r"\b(?:все\s+)?pdf[- ]?файл\w*\b", {".pdf"}),
    ]
    for pattern, extensions in ext_groups:
        if re.search(pattern, text):
            filters["extensions"] = extensions
            text = re.sub(pattern, " ", text)

    # Уточнение расширения, уже поддержанное прежней версией.
    explicit = re.search(r"\.(pdf|docx?|xlsx?|pptx?|txt|jpg|jpeg|png|zip|rar|7z|mp4|mkv|avi|mov)\b", text)
    if explicit:
        filters["extensions"] = {"." + explicit.group(1)}
        text = text.replace(explicit.group(0), " ")

    # Область поиска: буква диска или стандартные пользовательские каталоги.
    drive = re.search(r"\b(?:на\s+)?диск[еа]?\s+([a-z])\b", text)
    if drive:
        filters["drive"] = drive.group(1).upper() + ":"
        text = text[:drive.start()] + " " + text[drive.end():]
    folder_patterns = [
        (r"\b(?:в\s+)?загрузк\w*\b", "downloads"),
        (r"\b(?:на\s+)?рабочем\s+столе\b", "desktop"),
        (r"\b(?:в\s+)?документ\w*\b", "documents"),
        (r"\b(?:в\s+)?изображени\w*\b", "pictures"),
    ]
    for pattern, folder in folder_patterns:
        match = re.search(pattern, text)
        if match:
            filters["folder"] = folder
            text = text[:match.start()] + " " + text[match.end():]
            break

    # Периоды дат; для "созданные" используется creation time (Windows ctime).
    if re.search(r"\bсозданн\w*\b", text):
        filters["date_field"] = "ctime"
    if re.search(r"\b(?:сегодня|за\s+сегодня|сегодняшн\w*)\b", text):
        filters["start"], filters["end"] = now.replace(hour=0, minute=0, second=0, microsecond=0), now.replace(hour=23, minute=59, second=59, microsecond=999999)
        text = re.sub(r"\b(?:за\s+)?сегодняшн\w*|\bсегодня\b", " ", text)
    elif re.search(r"\b(?:вчера|вчерашн\w*)\b", text):
        day = (now - timedelta(days=1)).date()
        filters["start"] = datetime.combine(day, datetime.min.time())
        filters["end"] = datetime.combine(day, datetime.max.time())
        text = re.sub(r"\bвчерашн\w*|\bвчера\b", " ", text)
    elif re.search(r"\b(?:прошл\w*\s+недел\w*|последн\w*\s+7\s+дн\w*)\b", text):
        filters["start"] = now - timedelta(days=7)
        filters["end"] = now
        text = re.sub(r"\bпрошл\w*\s+недел\w*|\bпоследн\w*\s+7\s+дн\w*", " ", text)
    elif re.search(r"\b(?:прошл\w*\s+месяц|за\s+месяц)\b", text):
        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        filters["end"] = first_this - timedelta(microseconds=1)
        filters["start"] = filters["end"].replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        text = re.sub(r"\b(?:прошл\w*\s+месяц|за\s+месяц)\b", " ", text)
    else:
        months = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "май": 5, "июн": 6,
                  "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
        for stem, month in months.items():
            month_pattern = r"\b(?:май|мая)\b" if stem == "май" else r"\b" + stem + r"[а-я]*\b"
            m = re.search(month_pattern, text)
            if m:
                year_match = re.search(r"\b(20\d{2})\b", text)
                year = int(year_match.group(1)) if year_match else now.year
                if year_match:
                    text = text[:year_match.start()] + " " + text[year_match.end():]
                filters["start"] = datetime(year, month, 1)
                next_month = datetime(year + (month == 12), month % 12 + 1, 1)
                filters["end"] = next_month - timedelta(microseconds=1)
                text = text[:m.start()] + " " + text[m.end():]
                break

    # Разговорные единицы без числового значения означают один гигабайт/мегабайт.
    word_size = re.search(r"\b(больше|свыше|крупнее|меньше|до)\s+(гигабайт\w*|гиг\w*|мегабайт\w*|мег\w*)\b", text)
    if word_size:
        value = 1024**3 if word_size.group(2).startswith(("гига", "гиг")) else 1024**2
        if word_size.group(1) in ("больше", "свыше", "крупнее"):
            filters["min_size"] = value
        else:
            filters["max_size"] = value
        text = text[:word_size.start()] + " " + text[word_size.end():]

    # Числительные словами в условиях размера: «больше одного ГБ» -> «больше 1 ГБ».
    number_words = {
        "один": "1", "одного": "1", "одна": "1", "одной": "1", "одно": "1", "одну": "1",
        "два": "2", "две": "2", "двух": "2", "двум": "2",
        "три": "3", "трех": "3", "трем": "3",
        "четыре": "4", "четырех": "4", "четырем": "4",
        "пять": "5", "пяти": "5",
        "шесть": "6", "шести": "6",
        "семь": "7", "семи": "7",
        "восемь": "8", "восьми": "8",
        "девять": "9", "девяти": "9",
        "десять": "10", "десяти": "10",
    }
    number_pattern = r"\b(больше|свыше|крупнее|меньше|до|равен|равна|равно|равны|ровно)\s+(" + "|".join(
        sorted(number_words, key=len, reverse=True)
    ) + r")(?=\s+(?:байт\w*|б|кб|кбайт\w*|мб|мбайт\w*|мегабайт\w*|гб|гбайт\w*|гигабайт\w*)\b)"
    text = re.sub(
        number_pattern,
        lambda match: match.group(1) + " " + number_words[match.group(2)],
        text,
    )

    # Размер: поддерживаются байты, КБ, МБ и ГБ.
    size_re = re.search(r"\b(больше|свыше|крупнее|меньше|до|равен\w*|равн\w*|ровно)\s+(\d+(?:[.,]\d+)?)\s*(байт\w*|б|кб|кбайт\w*|мб|мбайт\w*|мегабайт\w*|гб|гбайт\w*|гигабайт\w*)?\b", text)
    if size_re:
        amount = float(size_re.group(2).replace(",", "."))
        unit = (size_re.group(3) or "мб").casefold()
        multiplier = 1 if unit.startswith(("б", "байт")) else 1024 if unit.startswith("к") else 1024**3 if unit.startswith(("г", "гига")) else 1024**2
        size = int(amount * multiplier)
        if size_re.group(1).startswith(("равн", "ровно")):
            filters["exact_size"] = size
        elif size_re.group(1) in ("больше", "свыше", "крупнее"):
            filters["min_size"] = size
        else:
            filters["max_size"] = size
        text = text[:size_re.start()] + " " + text[size_re.end():]
    if re.search(r"\b(?:большие|крупные|самые\s+большие)\s+файл\w*\b", text):
        filters["sort"] = "size_desc"
    if re.search(r"\b(?:маленькие|мелкие|самые\s+маленькие)\s+файл\w*\b", text):
        filters["sort"] = "size_asc"
    if re.search(r"\b(?:последние|новые|недавние)\s+(?:документ\w*|файл\w*)\b", text):
        filters["sort"] = "date_desc"
    if re.search(r"\b(?:старые|самые\s+старые)\s+(?:документ\w*|файл\w*)\b", text):
        filters["sort"] = "date_asc"

    # Служебные слова не должны становиться частью имени.
    text = re.sub(r"\b(?:найди|поищи|найти|поискать|мне|все|всех|файл\w*|документ\w*|документы|за|на|больше|свыше|крупнее|меньше|до|равен\\w*|равн\\w*|ровно|мегабайт\w*|гигабайт\w*|мб|гб|байт\w*|созданн\w*|измененн\w*|изменен\w*|последние|новые|недавние|самые|большие|маленькие|старые)\b", " ", text)
    stop_words = {"по", "для", "при", "это", "как", "или", "его", "ее", "их", "те", "которые", "который", "которая", "которое", "которых", "равен", "равна", "равно", "равны", "ровно", "копию", "копия", "названию", "название", "имя", "имени", "формат", "формата", "формате", "форматов", "форматах", "типе", "виде"}
    raw_terms = [part for part in re.findall(r"[a-zа-яё0-9_.-]+", text) if (len(part) > 1 or part.isdigit()) and part not in stop_words]
    suffixes = ("иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими", "ную", "ую", "юю", "ая", "яя", "ое", "ее", "ые", "ие", "ый", "ий", "ой", "ым", "им", "ом", "ем", "ах", "ях", "ов", "ев", "ей", "ам", "ям", "ую", "ию", "ия", "ья", "ью", "а", "я", "ы", "и", "у", "ю", "е", "о")
    terms = []
    for term in raw_terms:
        stem = term
        if re.search(r"[а-яё]", stem):
            for suffix in suffixes:
                if stem.endswith(suffix) and len(stem) - len(suffix) >= 3:
                    stem = stem[:-len(suffix)]
                    break
        terms.append(stem)
    return {"terms": terms, "filters": filters}


def _search_worker(query: str, parent):
    from datetime import datetime
    parsed = _parse_search_request(query)
    filters = parsed["filters"]
    terms = parsed["terms"]
    extension = next(iter(filters["extensions"])) if filters["extensions"] and len(filters["extensions"]) == 1 else None
    display_query = query
    if extension and not terms:
        display_query = "*" + extension
    elif extension:
        display_query = "*" + " ".join(terms) + "*" + extension
    print(f"Ищу «{display_query}» по MFT и SQLite. Первое индексирование может занять некоторое время...", flush=True)
    try:
        if terms:
            result_sets = [set(refresh_and_search(term, report=lambda message: print(f"[Поиск файлов] {message}", flush=True))) for term in terms]
            matches = list(set.intersection(*result_sets)) if result_sets else []
        else:
            if filters["extensions"]:
                result_sets = [
                    set(refresh_and_search("__EXT__:" + ext, report=lambda message: print(f"[Поиск файлов] {message}", flush=True)))
                    for ext in sorted(filters["extensions"])
                ]
                matches = list(set.union(*result_sets)) if result_sets else []
            else:
                empty_query = "__SORT_SIZE_DESC__" if filters["sort"] == "size_desc" else "__SORT_SIZE_ASC__" if filters["sort"] == "size_asc" else "__ALL_FILTERED__" if any((filters["start"], filters["end"], filters["drive"], filters["folder"], filters["min_size"], filters["max_size"], filters["exact_size"])) else ""
                matches = refresh_and_search(empty_query, report=lambda message: print(f"[Поиск файлов] {message}", flush=True))

        filtered = []
        for path in matches:
            try:
                stat = path.stat()
                size = stat.st_size
                timestamp = stat.st_ctime if filters["date_field"] == "ctime" else stat.st_mtime
                if filters["extensions"] and path.suffix.casefold() not in filters["extensions"]:
                    continue
                if filters["drive"] and (not path.drive or path.drive.upper() != filters["drive"]):
                    continue
                if filters["folder"]:
                    home = Path.home()
                    roots = {
                        "downloads": home / "Downloads",
                        "desktop": home / "Desktop",
                        "documents": home / "Documents",
                        "pictures": home / "Pictures",
                    }
                    try:
                        path.resolve().relative_to(roots[filters["folder"]].resolve())
                    except (ValueError, OSError):
                        continue
                if filters["min_size"] is not None and size <= filters["min_size"]:
                    continue
                if filters["max_size"] is not None and size >= filters["max_size"]:
                    continue
                if filters["exact_size"] is not None and size != filters["exact_size"]:
                    continue
                if filters["start"] and datetime.fromtimestamp(timestamp) < filters["start"]:
                    continue
                if filters["end"] and datetime.fromtimestamp(timestamp) > filters["end"]:
                    continue
                filtered.append((path, size, stat.st_mtime, stat.st_ctime))
            except (OSError, ValueError):
                continue

        sort_mode = filters["sort"]
        if sort_mode == "size_desc":
            filtered.sort(key=lambda item: item[1], reverse=True)
        elif sort_mode == "size_asc":
            filtered.sort(key=lambda item: item[1])
        elif sort_mode == "date_asc":
            filtered.sort(key=lambda item: item[2])
        elif sort_mode == "date_desc" or filters["start"] or filters["end"]:
            filtered.sort(key=lambda item: item[2], reverse=True)
        matches = [(item[0], item[3], item[1]) for item in filtered]
        _search_results.put(("success", parent, (display_query, matches)))
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


def show_file_results(parent, results: list[tuple[Path, float, int]], query: str):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from datetime import datetime
    from dialog_utils import activate_modal

    window = tk.Toplevel(parent)
    window.title(f"Результаты поиска: {query}")
    window.geometry("1000x500")
    window.minsize(650, 300)
    window.transient(parent)
    ttk.Label(
        window,
        text=f"Найдено файлов: {len(results)}. Двойной щелчок — открыть файл.",
    ).pack(anchor="w", padx=12, pady=(12, 6))

    frame = ttk.Frame(window)
    frame.pack(fill="both", expand=True, padx=12, pady=6)
    columns = ("file", "created", "size")
    listing = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
    listing.heading("file", text="Файл")
    listing.heading("created", text="Дата создания")
    listing.heading("size", text="Размер")
    listing.column("file", width=610, minwidth=260, stretch=True)
    listing.column("created", width=155, minwidth=135, stretch=False, anchor="center")
    listing.column("size", width=110, minwidth=95, stretch=False, anchor="e")

    y_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=listing.yview)
    x_scrollbar = ttk.Scrollbar(frame, orient="horizontal", command=listing.xview)
    listing.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
    listing.grid(row=0, column=0, sticky="nsew")
    y_scrollbar.grid(row=0, column=1, sticky="ns")
    x_scrollbar.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

    def format_size(value: int) -> str:
        amount = float(value)
        for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
            if amount < 1024 or unit == "ТБ":
                return f"{amount:.0f} {unit}" if unit == "Б" else f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{value} Б"

    paths = []
    for index, (path, created_at, size) in enumerate(results):
        paths.append(path)
        try:
            created_text = datetime.fromtimestamp(created_at).strftime("%d.%m.%Y %H:%M")
        except (OSError, OverflowError, ValueError):
            created_text = "—"
        listing.insert(
            "",
            "end",
            iid=str(index),
            values=(str(path), created_text, format_size(size)),
        )

    def open_selected(_event=None):
        selection = listing.selection()
        if selection:
            try:
                os.startfile(str(paths[int(selection[0])]))
            except OSError as exc:
                messagebox.showerror("Не удалось открыть файл", str(exc), parent=window)

    listing.bind("<Double-Button-1>", open_selected)
    ttk.Button(window, text="Открыть выбранный файл", command=open_selected).pack(pady=(0, 12))
    activate_modal(window, parent)
