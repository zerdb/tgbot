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
        yscrollincrement=29,
    )
    scrollbar = tk.Scrollbar(
        list_area,
        orient="vertical",
        command=canvas.yview,
    )
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    buttons = []
    button_height = 26
    button_gap = 3

    def resize_buttons(event):
        width = max(event.width - 2, 1)
        for item_id in buttons:
            canvas.itemconfigure(item_id, width=width)

    canvas.bind("<Configure>", resize_buttons)

    for index, (icon, name, path) in enumerate(PROJECTS):
        button = tk.Button(
            canvas,
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

        item_id = canvas.create_window(
            (0, index * (button_height + button_gap)),
            window=button,
            anchor="nw",
            width=450,
            height=button_height,
        )
        buttons.append(item_id)

    content_height = len(PROJECTS) * (button_height + button_gap)
    canvas.configure(scrollregion=(0, 0, 0, max(content_height, 1)))

    def scroll(event):
        if event.delta == 0:
            return

        # Windows: positive delta means wheel up.
        # Canvas yview_scroll(positive) moves the viewport down,
        # which moves the project list upward as expected.
        direction = 1 if event.delta > 0 else -1
        canvas.yview_scroll(direction, "units")

    def enable_wheel(_event):
        canvas.bind_all("<MouseWheel>", scroll)

    def disable_wheel(_event):
        canvas.unbind_all("<MouseWheel>")

    canvas.bind("<Enter>", enable_wheel)
    canvas.bind("<Leave>", disable_wheel)

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
