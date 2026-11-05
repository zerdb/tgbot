"""Compact main Tkinter window with dropdown command groups."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog


class AssistantWindow:
    def __init__(self, on_close, on_command, microphone_status="ПРОВЕРКА"):
        self.root = tk.Tk()
        self.root.title("GigaAM — голосовой помощник")
        self.root.geometry("760x570")
        self.root.minsize(620, 480)
        self.on_close = on_close
        self.on_command = on_command
        self.microphone_var = tk.StringVar(value=microphone_status)
        self.listening_var = tk.StringVar(value="ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
        self._recording_overlay = None
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Голосовой помощник GigaAM", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Распознавание речи работает локально на этом компьютере.").pack(anchor="w", pady=(2, 9))
        status = ttk.LabelFrame(outer, text="Состояние", padding=8)
        status.pack(fill="x", pady=(0, 9))
        ttk.Label(status, text="Микрофон:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(status, textvariable=self.microphone_var, foreground="#16723b").grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Label(status, text="Команды:", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w")
        ttk.Label(status, textvariable=self.listening_var, foreground="#1558a6").grid(row=0, column=3, sticky="w", padx=6)
        ttk.Label(outer, text="Горячие клавиши: диктовка — Right Ctrl + Right Shift; команда — Right Ctrl.",
                  wraplength=700).pack(anchor="w", pady=(0, 10))

        ttk.Label(outer, text="Опиши задачу своими словами", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 5))
        smart_row = ttk.Frame(outer)
        smart_row.pack(fill="x", pady=(0, 9))
        ttk.Button(smart_row, text="Умная команда…", command=self._ask_smart_command).pack(side="left")
        ttk.Label(smart_row, text="Например: перешли этот документ по почте").pack(side="left", padx=10)
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(0, 8))
        groups = [
            ("Windows ▾", [("Заблокировать компьютер", "заблокируй компьютер"), ("Перезагрузить компьютер", "перезагрузи компьютер"), ("Открыть загрузки", "открой загрузки"), ("Открыть настройки", "открой настройки"), ("Очистить корзину", "очисти корзину"), ("Сделать скриншот", "сделай скриншот")]),
            ("Файлы ▾", [("Найти файл", "найди файл"), ("Разобрать папку", "разбери папку"), ("Вставить таблицу в Excel", "перенеси в excel"), ("Сохранить как заметку", "сохрани как заметку")]),
            ("Интернет ▾", [("Поиск в интернете", "найди в интернете"), ("Создать напоминание", "напомни")]),
            ("Почта ▾", [("Новое письмо", "создай письмо"), ("Отправить файлы на почту", "отправить файлы на почту")]),
        ]
        for label, commands in groups:
            button = ttk.Menubutton(row, text=label)
            menu = tk.Menu(button, tearoff=False)
            for title, command in commands:
                menu.add_command(label=title, command=lambda c=command: self._click_command(c))
            button["menu"] = menu
            button.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Label(outer, text="Команды доступны голосом и через меню. Для поиска и напоминаний появится поле ввода.",
                  wraplength=700).pack(anchor="w")

    def _ask_smart_command(self):
        value = simpledialog.askstring("Умная команда", "Опиши задачу своими словами:", parent=self.root)
        if value and value.strip():
            self.on_command(value.strip())

    def _click_command(self, command):
        if command == "найди файл":
            value = simpledialog.askstring("Поиск файла", "Что найти? Укажите имя или часть имени:", parent=self.root)
            if value and value.strip():
                self.on_command("найди файл " + value.strip())
            return
        if command == "найди в интернете":
            value = simpledialog.askstring("Поиск в интернете", "Что найти в интернете?", parent=self.root)
            if value and value.strip():
                self.on_command("найди в интернете " + value.strip())
            return
        if command == "напомни":
            value = simpledialog.askstring("Новое напоминание", "Например: через 10 минут проверить духовку", parent=self.root)
            if value and value.strip():
                self.on_command("напомни " + value.strip())
            return
        if command == "перезагрузи компьютер" and not messagebox.askyesno("Подтвердите перезагрузку", "Перезагрузить компьютер сейчас?", parent=self.root):
            return
        if command == "очисти корзину" and not messagebox.askyesno("Подтвердите очистку", "Удалить содержимое корзины?", parent=self.root):
            return
        self.on_command(command)

    def set_recording_overlay(self, active, mode=None):
        def apply():
            if active:
                if self._recording_overlay is None or not self._recording_overlay.winfo_exists():
                    overlay = tk.Toplevel(self.root)
                    overlay.overrideredirect(True)
                    overlay.attributes("-topmost", True)
                    overlay.attributes("-alpha", 0.94)
                    overlay.configure(bg="#202124")
                    frame = tk.Frame(overlay, bg="#202124", padx=24, pady=18)
                    frame.pack()
                    tk.Label(frame, text="🎙", font=("Segoe UI Emoji", 46), fg="#ff3b30", bg="#202124").pack()
                    self._overlay_label = tk.Label(frame, text="", font=("Segoe UI", 11, "bold"), fg="white", bg="#202124")
                    self._overlay_label.pack(pady=(5, 0))
                    self._recording_overlay = overlay
                self._overlay_label.configure(text="СЛУШАЮ" if mode == "command" else "ДИКТОВКА")
                self._recording_overlay.update_idletasks()
                w, h = self._recording_overlay.winfo_reqwidth(), self._recording_overlay.winfo_reqheight()
                x = (self.root.winfo_screenwidth() - w) // 2
                y = (self.root.winfo_screenheight() - h) // 2
                self._recording_overlay.geometry(f"+{x}+{y}")
                self._recording_overlay.deiconify()
                self._recording_overlay.lift()
            elif self._recording_overlay is not None:
                self._recording_overlay.destroy()
                self._recording_overlay = None
                self._overlay_label = None
        try:
            self.root.after(0, apply)
        except tk.TclError:
            pass

    def set_status(self, listening=None, microphone=None):
        def apply():
            if listening is not None:
                self.listening_var.set(listening)
            if microphone is not None:
                self.microphone_var.set(microphone)
        try:
            self.root.after(0, apply)
        except tk.TclError:
            pass

    def run(self):
        self.root.mainloop()

    def close(self):
        self.on_close()
        self.root.destroy()
