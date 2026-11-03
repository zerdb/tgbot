"""Safe, preview-first organizer for files in one selected folder."""
from __future__ import annotations

import shutil
import tkinter as tk
from collections import defaultdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

CATEGORIES = {
    "Документы": {".doc", ".docx", ".odt", ".rtf", ".txt", ".pdf"},
    "Таблицы": {".xls", ".xlsx", ".ods", ".csv"},
    "Презентации": {".ppt", ".pptx", ".odp"},
    "Изображения": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".svg"},
    "Видео": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v"},
    "Аудио": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "Архивы": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "Установщики": {".exe", ".msi", ".msix", ".bat", ".cmd"},
}


def category_for(path: Path) -> str:
    for category, extensions in CATEGORIES.items():
        if path.suffix.lower() in extensions:
            return category
    return "Прочее"


def unique_destination(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    source = Path(filename)
    number = 2
    while True:
        candidate = directory / f"{source.stem} ({number}){source.suffix}"
        if not candidate.exists():
            return candidate
        number += 1


class FolderOrganizer:
    def __init__(self, parent=None):
        self.window = tk.Toplevel(parent) if parent else tk.Tk()
        self.window.title("Разбор папки")
        self.window.geometry("760x540")
        self.window.minsize(620, 420)
        self.folder: Path | None = None
        self.plan: list[tuple[Path, str]] = []
        self._build()

    def _build(self):
        outer = ttk.Frame(self.window, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Разбор папки", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Просмотрим файлы только в выбранной папке и предложим распределение по типам. "
                             "Ничего не перемещается без вашего подтверждения.",
                  wraplength=700).pack(anchor="w", pady=(4, 12))
        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Выбрать папку…", command=self.choose_folder).pack(side="left")
        self.folder_var = tk.StringVar(value="Папка не выбрана")
        ttk.Label(controls, textvariable=self.folder_var).pack(side="left", padx=10, fill="x", expand=True)
        self.tree = ttk.Treeview(outer, columns=("count", "examples"), show="tree headings")
        self.tree.heading("#0", text="Категория")
        self.tree.heading("count", text="Файлов")
        self.tree.heading("examples", text="Примеры")
        self.tree.column("#0", width=150)
        self.tree.column("count", width=70, anchor="center")
        self.tree.column("examples", width=440)
        self.tree.pack(fill="both", expand=True)
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(10, 0))
        self.status_var = tk.StringVar(value="Выберите папку для предварительного просмотра.")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left", fill="x", expand=True)
        self.organize_button = ttk.Button(footer, text="Разложить файлы", command=self.organize, state="disabled")
        self.organize_button.pack(side="right")

    def choose_folder(self):
        selected = filedialog.askdirectory(parent=self.window, title="Выберите папку для разбора")
        if selected:
            self.folder = Path(selected)
            self.folder_var.set(str(self.folder))
            self._scan()

    def _scan(self):
        self.plan.clear()
        groups: dict[str, list[str]] = defaultdict(list)
        try:
            for item in sorted(self.folder.iterdir(), key=lambda p: p.name.lower()):
                if item.is_file():
                    category = category_for(item)
                    self.plan.append((item, category))
                    if len(groups[category]) < 4:
                        groups[category].append(item.name)
        except OSError as exc:
            messagebox.showerror("Не удалось прочитать папку", str(exc), parent=self.window)
            return
        for row in self.tree.get_children():
            self.tree.delete(row)
        counts: dict[str, int] = defaultdict(int)
        for _, category in self.plan:
            counts[category] += 1
        for category in sorted(counts):
            examples = ", ".join(groups[category])
            if counts[category] > len(groups[category]):
                examples += ", …"
            self.tree.insert("", "end", text=category, values=(counts[category], examples))
        self.status_var.set(f"Найдено файлов: {len(self.plan)}. Вложенные папки не затрагиваются.")
        self.organize_button.configure(state="normal" if self.plan else "disabled")

    def organize(self):
        if not self.folder or not self.plan:
            return
        if not messagebox.askyesno("Подтвердите разбор",
            f"Создать папки категорий и переместить {len(self.plan)} файлов?\n\n"
            "Существующие файлы не перезаписываются. Вложенные папки не затрагиваются.",
            parent=self.window):
            return
        moved, errors = 0, []
        for source, category in self.plan:
            try:
                target_dir = self.folder / category
                target_dir.mkdir(exist_ok=True)
                shutil.move(str(source), str(unique_destination(target_dir, source.name)))
                moved += 1
            except OSError as exc:
                errors.append(f"{source.name}: {exc}")
        self._scan()
        if errors:
            messagebox.showwarning("Разбор завершён не полностью",
                f"Перемещено: {moved}. Ошибок: {len(errors)}.\n\n" + "\n".join(errors[:8]),
                parent=self.window)
        else:
            messagebox.showinfo("Готово", f"Разложено файлов: {moved}.", parent=self.window)
        self.status_var.set(f"Перемещено файлов: {moved}. Ошибок: {len(errors)}.")


def open_folder_organizer(parent=None):
    FolderOrganizer(parent)
