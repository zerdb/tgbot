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
    )

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    button_height = 26
    button_gap = 3
    item_step = button_height + button_gap
    buttons = []
    scroll_offset = 0
    viewport_height = 1

    def max_scroll():
        content_height = len(buttons) * item_step
        return max(0, content_height - viewport_height)

    def update_scrollbar():
        maximum = max_scroll()
        if maximum <= 0:
            scrollbar.set(0, 1)
        else:
            first = scroll_offset / (maximum + viewport_height)
            last = (scroll_offset + viewport_height) / (maximum + viewport_height)
            scrollbar.set(first, min(last, 1))

    def place_buttons():
        for index, item_id in enumerate(buttons):
            canvas.coords(
                item_id,
                0,
                index * item_step - scroll_offset,
            )
        update_scrollbar()

    def on_resize(event):
        nonlocal viewport_height
        viewport_height = max(event.height, 1)
        width = max(event.width - 2, 1)

        for item_id in buttons:
            canvas.itemconfigure(item_id, width=width)

        nonlocal scroll_offset
        scroll_offset = min(scroll_offset, max_scroll())
        place_buttons()

    canvas.bind("<Configure>", on_resize)

    def scroll_units(units):
        nonlocal scroll_offset
        scroll_offset = max(
            0,
            min(scroll_offset + units * item_step, max_scroll()),
        )
        place_buttons()

    def on_wheel(event):
        if event.delta:
            units = -1 if event.delta > 0 else 1
            scroll_units(units)

    def on_scrollbar(*args):
        nonlocal scroll_offset

        maximum = max_scroll()
        if maximum <= 0:
            scroll_offset = 0
            place_buttons()
            return

        if args[0] == "moveto":
            fraction = max(0.0, min(float(args[1]), 1.0))
            scroll_offset = round(fraction * maximum)
            place_buttons()
        elif args[0] == "scroll":
            amount = int(args[1])
            scroll_units(amount)

    scrollbar.configure(command=on_scrollbar)

    for icon, name, path in PROJECTS:
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
            (0, 0),
            window=button,
            anchor="nw",
            width=450,
            height=button_height,
        )
        buttons.append(item_id)

    canvas.bind("<MouseWheel>", on_wheel)
    canvas.bind("<Enter>", lambda _event: canvas.focus_set())

    tk.Label(
        root,
        text="Выбери приложение — оно запустится в отдельном окне",
        font=("Segoe UI", 9),
        fg="#6b7280",
        bg="#111827",
    ).pack(pady=(0, 12))

    root.after_idle(place_buttons)
    root.mainloop()


if __name__ == "__main__":
    main()
