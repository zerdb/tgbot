"""AI-assisted full-text search across local documents (read-only)."""
from __future__ import annotations

import os
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from dialog_utils import activate_modal

SUPPORTED = {".txt", ".md", ".py", ".csv", ".log", ".pdf", ".docx", ".xlsx"}
MAX_FILE_BYTES = 8 * 1024 * 1024


def _extract(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".py", ".csv", ".log"}:
        return path.read_text(encoding="utf-8", errors="replace")[:100000]
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:30])[:100000]
    if suffix == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(str(path)).paragraphs)[:100000]
    if suffix == ".xlsx":
        from openpyxl import load_workbook
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            chunks = []
            for sheet in workbook.worksheets[:10]:
                for row in sheet.iter_rows(max_row=200, values_only=True):
                    line = " ".join(str(value) for value in row if value is not None)
                    if line:
                        chunks.append(line)
            return "\n".join(chunks)[:100000]
        finally:
            workbook.close()
    return ""


def _find_candidates(folder: Path, query: str):
    tokens = [token.casefold() for token in re.findall(r"[\wа-яё]{3,}", query, re.I)]
    if not tokens:
        raise ValueError("Запрос должен содержать слово длиной от трёх символов.")
    found = []
    for path in folder.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = _extract(path)
        except Exception:
            continue
        normalized = text.casefold()
        score = sum(normalized.count(token) for token in tokens)
        if score:
            found.append((score, path, text[:12000]))
    return sorted(found, key=lambda item: item[0], reverse=True)[:8]


def open_document_search(parent):
    if parent is None:
        return

    def show():
        if not parent.winfo_exists():
            return
        window = tk.Toplevel(parent)
        window.title("ИИ-поиск по документам")
        window.geometry("820x600")
        window.minsize(650, 480)
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Найти информацию внутри документов", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        folder_var = tk.StringVar(value=str(Path.home() / "Documents"))
        query_var = tk.StringVar()
        folder_row = ttk.Frame(frame)
        folder_row.pack(fill="x", pady=(10, 6))
        ttk.Entry(folder_row, textvariable=folder_var).pack(side="left", fill="x", expand=True)
        def choose():
            value = filedialog.askdirectory(parent=window, title="Выбери папку для поиска")
            if value:
                folder_var.set(value)
        ttk.Button(folder_row, text="Обзор…", command=choose).pack(side="left", padx=(8, 0))
        ttk.Label(frame, text="Что нужно найти?").pack(anchor="w")
        ttk.Entry(frame, textvariable=query_var).pack(fill="x", pady=(3, 8))
        ttk.Label(frame, text="Ищет по содержимому TXT, PDF, Word, Excel, Markdown, CSV и исходников. Файлы не изменяются.", wraplength=760).pack(anchor="w")
        ttk.Label(frame, text="Важно: найденные фрагменты будут отправлены подключённой модели OpenRouter для анализа. Не выбирай папки с конфиденциальными документами.", wraplength=760).pack(anchor="w", pady=(3, 6))
        output = tk.Text(frame, wrap="word", height=18, font=("Segoe UI", 10))
        output.pack(fill="both", expand=True, pady=8)
        status = tk.StringVar(value="Выбери папку и введи запрос.")
        ttk.Label(frame, textvariable=status).pack(anchor="w")

        def run_search():
            folder_text, query = folder_var.get().strip(), query_var.get().strip()
            folder = Path(folder_text).expanduser()
            if not folder.is_dir() or not query:
                messagebox.showwarning("Поиск", "Выбери существующую папку и введи запрос.", parent=window)
                return
            search_button.configure(state="disabled")
            output.delete("1.0", "end")
            status.set("Просматриваю документы…")
            def worker():
                try:
                    candidates = _find_candidates(folder, query)
                    if not candidates:
                        answer = "Совпадений в поддерживаемых документах не найдено."
                    else:
                        from ai_chat import ask_ai
                        context = "\n\n".join(
                            f"ФАЙЛ: {path}\nФРАГМЕНТ:\n{content}" for _score, path, content in candidates
                        )
                        answer = ask_ai(
                            "Найди ответ на запрос пользователя, опираясь только на приведённые документы. "
                            "Укажи названия файлов и не додумывай отсутствующие факты. "
                            f"Запрос: {query}\n\nДокументы:\n{context[:26000]}",
                            remember=False,
                        )
                    result = (candidates if 'candidates' in locals() else [], answer, None)
                except Exception as exc:
                    result = ([], None, str(exc))
                def finish():
                    if not window.winfo_exists():
                        return
                    search_button.configure(state="normal")
                    candidates, answer, error = result
                    if error:
                        status.set("Поиск завершился с ошибкой.")
                        output.insert("1.0", error)
                        return
                    status.set(f"Найдено документов: {len(candidates)}")
                    output.insert("1.0", answer)
                    if candidates:
                        output.insert("end", "\n\nИсточники:\n" + "\n".join(str(path) for _score, path, _content in candidates))
                try:
                    window.after(0, finish)
                except tk.TclError:
                    pass
            threading.Thread(target=worker, daemon=True, name="document-search").start()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        search_button = ttk.Button(buttons, text="Искать с ИИ", command=run_search)
        search_button.pack(side="left")
        ttk.Button(buttons, text="Закрыть", command=window.destroy).pack(side="right")
        activate_modal(window, parent)

    parent.after(0, show)
