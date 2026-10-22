import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

FILE_CATEGORIES = {
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

def get_category(path):
    ext = path.suffix.lower()
    for category, extensions in FILE_CATEGORIES.items():
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

class FileSorterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tkinter File Sorter")
        self.geometry("820x560")
        self.minsize(650, 450)
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
        lines = [f"{name}: {len(exts)} расширений" for name, exts in sorted(FILE_CATEGORIES.items())]
        messagebox.showinfo("Категории", "\n".join(lines))

    def sort_files(self):
        folder = Path(self.folder.get().strip())
        if not self.folder.get().strip() or not folder.is_dir():
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
                category = get_category(file)
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
