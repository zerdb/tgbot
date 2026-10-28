import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


ROOT = Path(__file__).resolve().parent
HIDE_CONSOLE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

PROJECTS = [
    ("🤖  Telegram Bot", ROOT / "telegram-bot" / "main.py"),
    ("🖼  Image Downloader", ROOT / "image-downloader" / "downloader.py"),
    ("💻  Telegram PC Bridge", ROOT / "telegram-pc-bridge" / "main.py"),
    ("📁  File Sorter", ROOT / "tkinter-file-sorter" / "tkinter_file_sorter.py"),
    ("📋  Life Manager", ROOT / "tkinter-life-manager" / "main.py"),
    ("🎮  Tetris", ROOT / "tkinter-tetris" / "tetris.py"),
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
    root.minsize(480, 520)
    root.configure(bg="#111827")

    header = tk.Frame(root, bg="#111827")
    header.pack(fill="x", padx=30, pady=(28, 10))

    tk.Label(
        header,
        text="TGBOT",
        font=("Segoe UI", 28, "bold"),
        fg="white",
        bg="#111827",
    ).pack(anchor="w")

    tk.Label(
        header,
        text="Главное окно проектов",
        font=("Segoe UI", 12),
        fg="#9ca3af",
        bg="#111827",
    ).pack(anchor="w", pady=(2, 0))

    card = tk.Frame(root, bg="#1f2937")
    card.pack(fill="both", expand=True, padx=30, pady=(15, 30))

    tk.Label(
        card,
        text="Запустить проект",
        font=("Segoe UI", 15, "bold"),
        fg="white",
        bg="#1f2937",
    ).pack(anchor="w", padx=22, pady=(22, 12))

    for name, path in PROJECTS:
        button = tk.Button(
            card,
            text=name,
            command=lambda p=path: launch(p),
            font=("Segoe UI", 11),
            fg="white",
            bg="#374151",
            activeforeground="white",
            activebackground="#4b5563",
            relief="flat",
            bd=0,
            cursor="hand2",
            anchor="w",
            padx=18,
            height=2,
        )
        button.pack(fill="x", padx=22, pady=5)

    tk.Label(
        root,
        text="Выбери приложение — оно запустится в отдельном окне",
        font=("Segoe UI", 9),
        fg="#6b7280",
        bg="#111827",
    ).pack(pady=(0, 15))

    root.mainloop()


if __name__ == "__main__":
    main()
