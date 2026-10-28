import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


ROOT = Path(__file__).resolve().parent
HIDE_CONSOLE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

PROJECTS = [
    ("🤖", "Telegram Bot", ROOT / "telegram-bot" / "main.py"),
    ("🖼", "Image Downloader", ROOT / "image-downloader" / "downloader.py"),
    ("💻", "Telegram PC Bridge", ROOT / "telegram-pc-bridge" / "main.py"),
    ("📁", "File Sorter", ROOT / "tkinter-file-sorter" / "tkinter_file_sorter.py"),
    ("📋", "Life Manager", ROOT / "tkinter-life-manager" / "main.py"),
    ("🎮", "Tetris", ROOT / "tkinter-tetris" / "tetris.py"),
]


def launch(path: Path) -> None:
    if not path.exists():
        messagebox.showerror(
            "Файл не найден",
            f"Проект не найден:\n\n{path}",
        )
        return

    try:
        subprocess.Popen(
            [sys.executable, str(path)],
            cwd=str(path.parent),
            creationflags=HIDE_CONSOLE,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        messagebox.showerror(
            "Ошибка запуска",
            f"Не удалось запустить проект:\n\n{exc}",
        )


def main() -> None:
    root = tk.Tk()
    root.title("TGBOT • Project Launcher")
    root.geometry("520x560")
    root.minsize(480, 500)
    root.configure(bg="#111827")

    header = tk.Frame(root, bg="#111827")
    header.pack(fill="x", padx=28, pady=(24, 8))

    tk.Label(
        header,
        text="TGBOT",
        font=("Segoe UI", 25, "bold"),
        fg="white",
        bg="#111827",
    ).pack(anchor="w")

    tk.Label(
        header,
        text="Главное окно проектов",
        font=("Segoe UI", 11),
        fg="#9ca3af",
        bg="#111827",
    ).pack(anchor="w", pady=(1, 0))

    card = tk.Frame(root, bg="#1f2937")
    card.pack(fill="both", expand=True, padx=28, pady=(12, 22))

    tk.Label(
        card,
        text="Запустить проект",
        font=("Segoe UI", 13, "bold"),
        fg="white",
        bg="#1f2937",
    ).pack(anchor="w", padx=18, pady=(16, 9))

    list_area = tk.Frame(card, bg="#1f2937")
    list_area.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    canvas = tk.Canvas(
        list_area,
        bg="#1f2937",
        highlightthickness=0,
        bd=0,
    )
    scrollbar = tk.Scrollbar(
        list_area,
        orient="vertical",
        command=canvas.yview,
    )
    project_frame = tk.Frame(canvas, bg="#1f2937")

    window_id = canvas.create_window((0, 0), window=project_frame, anchor="nw")

    def update_scroll_region(_event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def resize_project_frame(event):
        canvas.itemconfigure(window_id, width=event.width)

    project_frame.bind("<Configure>", update_scroll_region)
    canvas.bind("<Configure>", resize_project_frame)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def scroll(event):
        canvas.yview_scroll(int(-event.delta / 120), "units")

    canvas.bind_all("<MouseWheel>", scroll)

    for icon, name, path in PROJECTS:
        button = tk.Button(
            project_frame,
            text=f"  {icon}   {name}",
            command=lambda p=path: launch(p),
            font=("Segoe UI", 10),
            fg="white",
            bg="#374151",
            activeforeground="white",
            activebackground="#4b5563",
            relief="flat",
            bd=0,
            cursor="hand2",
            anchor="w",
            padx=10,
            height=1,
        )
        button.pack(fill="x", pady=3)

    tk.Label(
        root,
        text="Выбери приложение — оно запустится в отдельном окне",
        font=("Segoe UI", 9),
        fg="#6b7280",
        bg="#111827",
    ).pack(pady=(0, 12))

    root.mainloop()


if __name__ == "__main__":
    main()
