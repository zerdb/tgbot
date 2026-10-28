import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


ROOT = Path(__file__).resolve().parent


PROJECTS = [
    ("Telegram Bot", ROOT / "telegram-bot" / "main.py"),
    ("Image Downloader", ROOT / "image-downloader" / "downloader.py"),
    ("Telegram PC Bridge", ROOT / "telegram-pc-bridge" / "main.py"),
    ("File Sorter", ROOT / "tkinter-file-sorter" / "tkinter_file_sorter.py"),
    ("Life Manager", ROOT / "tkinter-life-manager" / "main.py"),
    ("Tetris", ROOT / "tkinter-tetris" / "tetris.py"),
]


def launch(path: Path) -> None:
    if not path.exists():
        messagebox.showerror("Ошибка", f"Файл проекта не найден:\n{path}")
        return

    try:
        subprocess.Popen(
            [sys.executable, str(path)],
            cwd=str(path.parent),
        )
    except Exception as exc:
        messagebox.showerror("Ошибка запуска", f"Не удалось запустить проект:\n{exc}")


def main() -> None:
    root = tk.Tk()
    root.title("tgbot — Project Launcher")
    root.geometry("430x430")
    root.resizable(False, False)

    title = tk.Label(
        root,
        text="Мои проекты",
        font=("Segoe UI", 20, "bold"),
        pady=18,
    )
    title.pack()

    subtitle = tk.Label(
        root,
        text="Выбери проект для запуска",
        font=("Segoe UI", 10),
    )
    subtitle.pack(pady=(0, 14))

    frame = tk.Frame(root)
    frame.pack(fill="both", expand=True, padx=35)

    for name, path in PROJECTS:
        button = tk.Button(
            frame,
            text=name,
            font=("Segoe UI", 11),
            height=2,
            command=lambda p=path: launch(p),
        )
        button.pack(fill="x", pady=5)

    root.mainloop()


if __name__ == "__main__":
    main()
