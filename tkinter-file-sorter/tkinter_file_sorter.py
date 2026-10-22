import json
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

DEFAULT_CATEGORIES = {
    "Documents": [".doc", ".docx", ".odt", ".rtf", ".txt", ".pdf", ".md"],
    "Spreadsheets": [".xls", ".xlsx", ".ods", ".csv", ".tsv"],
    "Presentations": [".ppt", ".pptx", ".odp", ".key"],
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".tiff", ".webp", ".ico", ".heic"],
    "Audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus"],
    "Video": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".mpeg", ".mpg", ".m4v"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"],
    "Source Code": [".py", ".js", ".html", ".css", ".cpp", ".c", ".h", ".java", ".php", ".rb", ".go", ".rs", ".ts", ".json", ".xml", ".yaml", ".yml", ".toml", ".sql", ".sh", ".bat", ".ps1"],
    "Executables": [".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".app"],
    "Databases": [".db", ".sqlite", ".sqlite3", ".mdb", ".accdb", ".sql"],
    "Ebooks": [".epub", ".mobi", ".azw", ".azw3", ".fb2", ".djvu"],
    "Torrents": [".torrent"],
    "Subtitles": [".srt", ".ass", ".ssa", ".sub", ".vtt"],
    "Fonts": [".ttf", ".otf", ".fon", ".woff", ".woff2"],
}

CONFIG_FILE = Path.home() / ".tkinter_file_sorter_categories.json"


def normalize_extensions(text):
    result = []
    for item in text.replace(";", ",").split(","):
        ext = item.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        if ext not in result:
            result.append(ext)
    return result


def load_categories():
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(name): list(exts) for name, exts in data.items()}
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return {name: exts.copy() for name, exts in DEFAULT_CATEGORIES.items()}


def save_categories(categories):
    CONFIG_FILE.write_text(
        json.dumps(categories, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_category(path, categories):
    ext = path.suffix.lower()
    for category, extensions in categories.items():
        if ext in extensions:
            return category
    return "Other"


def unique_destination(folder, file):
    destination = folder / file.name
    number = 1
    while destination.exists():
        destination = folder / f"{file.stem}_{number}{file.suffix}"
        number += 1
    return destination


class CategoryEditor(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.app = parent
        self.title("Редактор категорий")
        self.geometry("760x470")
        self.minsize(650, 400)
        self.transient(parent)

        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Категории", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")

        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True, pady=(6, 8))
        self.listbox = tk.Listbox(list_frame, exportselection=False)
        scroll = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        left_buttons = ttk.Frame(left)
        left_buttons.pack(fill="x")
        ttk.Button(left_buttons, text="Добавить", command=self.add_category).pack(side="left")
        ttk.Button(left_buttons, text="Переименовать", command=self.rename_category).pack(side="left", padx=6)
        ttk.Button(left_buttons, text="Удалить", command=self.delete_category).pack(side="left")

        right = ttk.Frame(main, padding=(16, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="Расширения выбранной категории", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        ttk.Label(right, text="Через запятую. Можно вводить с точкой или без неё.").pack(anchor="w", pady=(3, 6))

        self.extensions = tk.Text(right, height=14, wrap="word")
        self.extensions.pack(fill="both", expand=True)

        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Сохранить расширения", command=self.save_extensions).pack(side="left")
        ttk.Button(actions, text="Сбросить всё", command=self.reset_defaults).pack(side="left", padx=6)
        ttk.Button(actions, text="Закрыть", command=self.destroy).pack(side="right")

        self.refresh()

    def selected_name(self):
        selection = self.listbox.curselection()
        if not selection:
            return None
        return self.listbox.get(selection[0])

    def refresh(self, select_name=None):
        self.listbox.delete(0, "end")
        names = sorted(self.app.categories, key=str.lower)
        for name in names:
            self.listbox.insert("end", name)
        if names:
            target = select_name if select_name in names else names[0]
            index = names.index(target)
            self.listbox.selection_set(index)
            self.listbox.see(index)
            self.on_select()

    def on_select(self, _event=None):
        name = self.selected_name()
        self.extensions.delete("1.0", "end")
        if name:
            self.extensions.insert("1.0", ", ".join(self.app.categories[name]))

    def persist(self):
        try:
            save_categories(self.app.categories)
            self.app.status.set("Настройки категорий сохранены")
        except OSError as error:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки:\n{error}", parent=self)

    def add_category(self):
        name = simpledialog.askstring("Новая категория", "Название категории:", parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.app.categories:
            messagebox.showwarning("Категория", "Такая категория уже существует.", parent=self)
            return
        self.app.categories[name] = []
        self.persist()
        self.refresh(name)

    def rename_category(self):
        old = self.selected_name()
        if not old:
            return
        new = simpledialog.askstring("Переименовать", "Новое название:", initialvalue=old, parent=self)
        if not new:
            return
        new = new.strip()
        if not new or new == old:
            return
        if new in self.app.categories:
            messagebox.showwarning("Категория", "Категория с таким названием уже есть.", parent=self)
            return
        items = self.app.categories.pop(old)
        self.app.categories[new] = items
        self.persist()
        self.refresh(new)

    def delete_category(self):
        name = self.selected_name()
        if not name:
            return
        if messagebox.askyesno("Удаление", f"Удалить категорию «{name}»?", parent=self):
            del self.app.categories[name]
            self.persist()
            self.refresh()

    def save_extensions(self):
        name = self.selected_name()
        if not name:
            messagebox.showwarning("Категория", "Выберите категорию.", parent=self)
            return
        extensions = normalize_extensions(self.extensions.get("1.0", "end"))
        self.app.categories[name] = extensions
        self.persist()
        messagebox.showinfo("Сохранено", f"Категория «{name}» обновлена.", parent=self)

    def reset_defaults(self):
        if not messagebox.askyesno("Сброс", "Вернуть стандартный набор категорий и расширений?", parent=self):
            return
        self.app.categories = {name: exts.copy() for name, exts in DEFAULT_CATEGORIES.items()}
        self.persist()
        self.refresh()


class FileSorterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tkinter File Sorter")
        self.geometry("820x560")
        self.minsize(650, 450)
        self.categories = load_categories()
        self.folder = tk.StringVar()
        self.status = tk.StringVar(value="Выберите папку для сортировки")
        self.build_ui()

    def build_ui(self):
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Файловый сортировщик", font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Сортировка файлов по типам — только Python и Tkinter.").pack(anchor="w", pady=(4, 16))

        picker = ttk.Frame(frame)
        picker.pack(fill="x")
        ttk.Entry(picker, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(picker, text="Выбрать папку", command=self.choose_folder).pack(side="left", padx=(8, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=12)
        ttk.Button(buttons, text="Сортировать", command=self.sort_files).pack(side="left")
        ttk.Button(buttons, text="Очистить лог", command=self.clear_log).pack(side="left", padx=8)
        ttk.Button(buttons, text="Категории", command=self.show_categories).pack(side="left")

        ttk.Label(frame, textvariable=self.status).pack(anchor="w", pady=(0, 8))

        log_frame = ttk.Frame(frame)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку")
        if folder:
            self.folder.set(folder)
            self.status.set(f"Выбрана папка: {folder}")

    def write_log(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.update_idletasks()

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def show_categories(self):
        CategoryEditor(self)

    def sort_files(self):
        raw = self.folder.get().strip()
        if not raw:
            messagebox.showwarning("Папка", "Выберите существующую папку.")
            return
        folder = Path(raw)
        if not folder.is_dir():
            messagebox.showwarning("Папка", "Выберите существующую папку.")
            return

        files = [item for item in folder.iterdir() if item.is_file()]
        if not files:
            messagebox.showinfo("Готово", "В папке нет файлов для сортировки.")
            return
        if not messagebox.askyesno("Подтверждение", f"Рассортировать {len(files)} файлов?"):
            return

        moved = errors = 0
        self.clear_log()
        for file in files:
            try:
                category = get_category(file, self.categories)
                target_folder = folder / category
                target_folder.mkdir(exist_ok=True)
                target = unique_destination(target_folder, file)
                shutil.move(str(file), str(target))
                moved += 1
                self.write_log(f"{file.name} -> {category}/{target.name}")
            except (OSError, shutil.Error) as error:
                errors += 1
                self.write_log(f"ОШИБКА {file.name}: {error}")

        self.status.set(f"Готово. Перемещено: {moved}; ошибок: {errors}")
        messagebox.showinfo("Готово", f"Перемещено: {moved}\nОшибок: {errors}")


if __name__ == "__main__":
    FileSorterApp().mainloop()
