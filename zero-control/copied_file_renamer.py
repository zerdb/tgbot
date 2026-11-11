"""AI-assisted, preview-first batch renaming for files copied in Windows Explorer."""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk
from uuid import uuid4

from clipboard_files import copied_file_paths
from dialog_utils import activate_modal, center_window, apply_modern_style


_INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\\\|?*]')
_RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _file_extension(path: Path) -> str:
    lower_name = path.name.casefold()
    for extension in (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst"):
        if lower_name.endswith(extension):
            return path.name[-len(extension):]
    return path.suffix


def _original_stem(path: Path) -> str:
    extension = _file_extension(path)
    return path.name[:-len(extension)] if extension else path.name


def validate_stem(value: str) -> str:
    """Validate a user-edited filename stem without changing its extension."""
    stem = str(value or "").strip()
    if not stem:
        raise ValueError("Новое имя не может быть пустым.")
    if _INVALID_WINDOWS_CHARS.search(stem) or any(ord(char) < 32 for char in stem):
        raise ValueError(f"Имя «{stem}» содержит недопустимые символы Windows.")
    if stem.endswith((".", " ")):
        raise ValueError(f"Имя «{stem}» не должно заканчиваться точкой или пробелом.")
    if stem.split(".", 1)[0].upper() in _RESERVED_WINDOWS_NAMES:
        raise ValueError(f"Имя «{stem}» зарезервировано Windows.")
    return stem


def _suggestion_stem(value: str, original: Path) -> str:
    """Convert a model suggestion into a safe editable stem."""
    candidate = str(value or "").strip().strip('"«»')
    extension = _file_extension(original)
    if extension and candidate.casefold().endswith(extension.casefold()):
        candidate = candidate[:-len(extension)]
    candidate = _INVALID_WINDOWS_CHARS.sub(" ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" .")
    if not candidate or candidate.split(".", 1)[0].upper() in _RESERVED_WINDOWS_NAMES:
        return _original_stem(original)
    return candidate[:160].rstrip(" .") or original.stem


def _suggest_batch(paths: list[Path]) -> list[str]:
    from groq_client import chat

    source = [
        {"index": index, "filename": path.name}
        for index, path in enumerate(paths)
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "Ты помогаешь аккуратно переименовать файлы. По исходному имени "
                "предложи короткое, понятное и информативное имя на русском языке. "
                "Не выдумывай содержимое файла и не добавляй даты или факты, которых "
                "нет в исходном имени. Сохраняй важные идентификаторы и смысл. "
                "Верни только JSON вида {\\"files\\":[{\\"index\\":0,\\"name\\":\\"Новое имя без расширения\\"}]}. "
                "Для каждого входного индекса верни ровно один вариант. Расширения не добавляй."
            ),
        },
        {"role": "user", "content": json.dumps(source, ensure_ascii=False)},
    ]
    answer = chat(
        messages,
        temperature=0.2,
        max_tokens=max(500, min(3000, len(paths) * 90)),
        response_format={"type": "json_object"},
    )
    try:
        payload = json.loads(answer)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", answer, re.DOTALL)
        if not match:
            raise RuntimeError("ИИ вернул ответ в неизвестном формате.")
        payload = json.loads(match.group(0))
    suggestions = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(suggestions, list):
        raise RuntimeError("ИИ не вернул список новых имён.")
    indexed = {}
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(paths):
            indexed[index] = _suggestion_stem(item.get("name", ""), paths[index])
    if len(indexed) != len(paths):
        raise RuntimeError("ИИ вернул не все варианты имён. Повтори команду.")
    return [indexed[index] for index in range(len(paths))]


def suggest_file_names(paths: list[Path]) -> list[str]:
    """Ask the configured Groq model for names in small batches based only on filenames."""
    result = []
    for start in range(0, len(paths), 25):
        result.extend(_suggest_batch(paths[start:start + 25]))
    return result


def rename_files(plan: list[tuple[Path, str]]) -> int:
    """Safely rename a batch, staging all sources first to support name swaps."""
    normalized = []
    source_keys = set()
    target_keys = set()
    for source_value, new_stem in plan:
        source = Path(source_value)
        if not source.is_file():
            raise RuntimeError(f"Файл больше не найден: {source}")
        source_key = _path_key(source)
        if source_key in source_keys:
            raise ValueError(f"Файл добавлен в список дважды: {source.name}")
        source_keys.add(source_key)
        editable_stem = str(new_stem or "").strip()
        extension = _file_extension(source)
        if extension and editable_stem.casefold().endswith(extension.casefold()):
            editable_stem = editable_stem[:-len(extension)].rstrip()
        stem = validate_stem(editable_stem)
        if len(stem + extension) > 255:
            raise ValueError(f"Новое имя файла слишком длинное: {stem + extension}")
        target = source.with_name(stem + extension)
        target_key = _path_key(target)
        if target_key in target_keys:
            raise ValueError(f"Несколько файлов получат имя «{target.name}». Исправь варианты.")
        target_keys.add(target_key)
        normalized.append((source, target))

    for source, target in normalized:
        if _path_key(source) == _path_key(target):
            continue
        if target.exists() and _path_key(target) not in source_keys:
            raise FileExistsError(f"Файл «{target.name}» уже существует и не выбран для переименования.")

    staged = []
    try:
        for source, target in normalized:
            if _path_key(source) == _path_key(target):
                continue
            temporary = source.with_name(f".{source.name}.zero-control-{uuid4().hex}.tmp")
            source.rename(temporary)
            staged.append((source, temporary, target))
    except Exception as exc:
        rollback_errors = []
        for source, temporary, _target in reversed(staged):
            try:
                temporary.rename(source)
            except OSError as rollback_exc:
                rollback_errors.append(f"{temporary.name}: {rollback_exc}")
        detail = (" Не удалось восстановить: " + "; ".join(rollback_errors)) if rollback_errors else ""
        raise RuntimeError(f"Не удалось подготовить файлы к переименованию: {exc}.{detail}") from exc

    completed = []
    try:
        for source, temporary, target in staged:
            temporary.rename(target)
            completed.append((source, target))
    except Exception as exc:
        rollback_errors = []
        for source, target in reversed(completed):
            try:
                target.rename(source)
            except OSError as rollback_exc:
                rollback_errors.append(f"{target.name}: {rollback_exc}")
        completed_sources = {_path_key(source) for source, _target in completed}
        for source, temporary, _target in reversed(staged):
            if _path_key(source) in completed_sources:
                continue
            try:
                if temporary.exists():
                    temporary.rename(source)
            except OSError as rollback_exc:
                rollback_errors.append(f"{temporary.name}: {rollback_exc}")
        detail = (" Ошибки восстановления: " + "; ".join(rollback_errors)) if rollback_errors else ""
        raise RuntimeError(f"Переименование прервано: {exc}.{detail}") from exc
    return len(completed)


class RenameReviewWindow:
    def __init__(self, parent, paths: list[Path], suggestions: list[str]):
        self.window = tk.Toplevel(parent)
        apply_modern_style(self.window)
        self.window.title("Zero Control — переименование файлов")
        self.window.geometry("900x650")
        self.window.minsize(680, 440)
        self.rows = []
        self._build(paths, suggestions)
        center_window(self.window, parent)
        activate_modal(self.window, parent)

    def _build(self, paths: list[Path], suggestions: list[str]):
        outer = ttk.Frame(self.window, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer, text="Понятные имена файлов",
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                f"Найдено файлов: {len(paths)}. Проверь предложения ИИ, при необходимости "
                "измени имя вручную или сними отметку с файла. Расширения сохраняются. "
                "Файлы не читаются — ИИ получил только их текущие имена."
            ),
            wraplength=840,
        ).pack(anchor="w", pady=(5, 12))

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 5))
        ttk.Label(header, text="Включить", width=10).pack(side="left")
        ttk.Label(header, text="Текущее имя", width=34).pack(side="left", padx=(4, 8))
        ttk.Label(header, text="Новое имя (без расширения)").pack(side="left")

        list_frame = ttk.Frame(outer)
        list_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        rows_frame = ttk.Frame(canvas)
        rows_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_window = canvas.create_window((0, 0), window=rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(canvas_window, width=event.width),
        )
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for index, (path, suggestion) in enumerate(zip(paths, suggestions)):
            row = ttk.Frame(rows_frame, padding=(4, 5))
            row.pack(fill="x")
            include = tk.BooleanVar(master=self.window, value=True)
            ttk.Checkbutton(row, variable=include).pack(side="left", padx=(0, 10))
            ttk.Label(
                row, text=path.name, width=34, wraplength=250,
            ).pack(side="left", padx=(0, 8), fill="x")
            name_frame = ttk.Frame(row)
            name_frame.pack(side="left", fill="x", expand=True)
            name_var = tk.StringVar(master=self.window, value=suggestion)
            ttk.Entry(name_frame, textvariable=name_var).pack(side="left", fill="x", expand=True)
            extension = _file_extension(path)
            if extension:
                ttk.Label(name_frame, text=extension).pack(side="left", padx=(5, 0))
            ttk.Separator(rows_frame, orient="horizontal").pack(fill="x")
            self.rows.append((path, include, name_var))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text="Отмена", command=self.window.destroy).pack(side="right")
        ttk.Button(
            footer, text="Подтвердить переименование",
            style="Accent.TButton", command=self._confirm,
        ).pack(side="right", padx=(0, 8))

    def _confirm(self):
        plan = [
            (path, name_var.get())
            for path, include, name_var in self.rows
            if include.get()
        ]
        if not plan:
            messagebox.showinfo("Нет выбранных файлов", "Отметь хотя бы один файл.", parent=self.window)
            return
        if not messagebox.askyesno(
            "Подтверждение переименования",
            f"Переименовать выбранные файлы: {len(plan)}?\n\n"
            "Содержимое файлов не изменяется.",
            parent=self.window,
        ):
            return
        try:
            count = rename_files(plan)
        except (ValueError, FileExistsError, RuntimeError) as exc:
            messagebox.showerror("Не удалось переименовать файлы", str(exc), parent=self.window)
            return
        messagebox.showinfo(
            "Готово",
            f"Переименовано файлов: {count}.",
            parent=self.window,
        )
        self.window.destroy()


def open_copied_file_renamer(parent):
    """Read Explorer's copied-file list, request consent, then show AI suggestions."""
    if parent is None or not parent.winfo_exists():
        return
    loading = tk.Toplevel(parent)
    apply_modern_style(loading)
    loading.title("Zero Control — переименование")
    loading.geometry("460x150")
    loading.transient(parent)
    body = ttk.Frame(loading, padding=18)
    body.pack(fill="both", expand=True)
    status = tk.StringVar(master=loading, value="Читаю список скопированных файлов…")
    ttk.Label(body, textvariable=status, wraplength=410).pack(fill="both", expand=True)
    center_window(loading, parent)
    activate_modal(loading, parent)

    def find_files(attempt=0):
        if not loading.winfo_exists():
            return
        paths = [Path(item) for item in copied_file_paths()]
        if paths:
            loading.destroy()
            if not messagebox.askyesno(
                "Передача имён файлов ИИ",
                f"Найдено файлов: {len(paths)}. Чтобы предложить понятные имена, "
                "Zero Control отправит подключённой модели ИИ только текущие имена "
                "файлов и их расширения. Содержимое файлов не читается и не отправляется.\n\n"
                "Продолжить?",
                parent=parent,
            ):
                return
            progress = tk.Toplevel(parent)
            apply_modern_style(progress)
            progress.title("Zero Control — ИИ")
            progress.geometry("440x140")
            progress.transient(parent)
            progress_body = ttk.Frame(progress, padding=18)
            progress_body.pack(fill="both", expand=True)
            ttk.Label(
                progress_body,
                text=f"ИИ подбирает понятные имена для {len(paths)} файлов…",
                wraplength=400,
            ).pack(fill="both", expand=True)
            center_window(progress, parent)
            activate_modal(progress, parent)

            def worker():
                try:
                    suggestions = suggest_file_names(paths)
                    result = (suggestions, None)
                except Exception as exc:
                    result = (None, str(exc))

                def finish():
                    if not progress.winfo_exists():
                        return
                    progress.destroy()
                    suggestions, error = result
                    if error:
                        messagebox.showerror(
                            "Не удалось получить предложения ИИ",
                            error,
                            parent=parent,
                        )
                        return
                    RenameReviewWindow(parent, paths, suggestions)

                try:
                    parent.after(0, finish)
                except tk.TclError:
                    pass

            threading.Thread(
                target=worker, daemon=True, name="copied-file-name-suggestions",
            ).start()
            return
        if attempt < 12:
            status.set("Проводник ещё не освободил буфер обмена. Повторяю…")
            loading.after(250, lambda: find_files(attempt + 1))
        else:
            loading.destroy()
            messagebox.showinfo(
                "Файлы не найдены",
                "Сначала выдели файлы в Проводнике и скопируй их (Ctrl+C), затем повтори команду.",
                parent=parent,
            )

    find_files()
