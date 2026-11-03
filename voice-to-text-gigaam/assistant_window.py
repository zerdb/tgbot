"""Main Tkinter window with clickable command shortcuts and live status."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog


class AssistantWindow:
    def __init__(self, on_close, on_command, microphone_status="ПРОВЕРКА"):
        self.root = tk.Tk()
        self.root.title("GigaAM — голосовой помощник")
        self.root.geometry("900x760")
        self.root.minsize(700, 580)
        self.on_close = on_close
        self.on_command = on_command
        self.microphone_var = tk.StringVar(value=microphone_status)
        self.listening_var = tk.StringVar(value="ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Голосовой помощник GigaAM", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Работает локально: распознавание речи выполняется на этом компьютере.").pack(anchor="w", pady=(2, 12))
        status = ttk.LabelFrame(outer, text="Состояние системы", padding=10)
        status.pack(fill="x", pady=(0, 12))
        ttk.Label(status, text="Микрофон:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(status, textvariable=self.microphone_var, foreground="#16723b").grid(row=0, column=1, sticky="w")
        ttk.Label(status, text="Прослушивание команд:", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        ttk.Label(status, textvariable=self.listening_var, foreground="#1558a6").grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(outer, text="Горячие клавиши", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Диктовка: Right Alt + Right Shift. Голосовая команда: Right Ctrl. "
                              "Если микрофон недоступен, используйте кнопки ниже.",
                  wraplength=840).pack(anchor="w", pady=(3, 10))
        ttk.Label(outer, text="Команды — нажмите для запуска", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        canvas_frame = ttk.Frame(outer)
        canvas_frame.pack(fill="both", expand=True, pady=(6, 8))
        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        button_frame = ttk.Frame(canvas, padding=(2, 2))
        button_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=button_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        groups = [
            ("Windows", [
                ("Заблокировать компьютер", "заблокируй компьютер"),
                ("Перезагрузить компьютер", "перезагрузи компьютер"),
                ("Открыть загрузки", "открой загрузки"),
                ("Открыть настройки", "открой настройки"),
                ("Очистить корзину", "очисти корзину"),
                ("Сделать скриншот", "сделай скриншот"),
            ]),
            ("Файлы и папки", [
                ("Найти файл", "найди файл"),
                ("Разобрать папку", "разбери папку"),
            ]),
            ("Интернет и напоминания", [
                ("Поиск в интернете", "найди в интернете"),
                ("Создать напоминание", "напомни"),
            ]),
            ("Контакты и почта", [
                ("Добавить контакт", "добавить контакт"),
                ("Показать контакты", "покажи контакты"),
                ("Новое письмо", "создай письмо"),
            ]),
        ]
        for group_name, commands in groups:
            group = ttk.LabelFrame(button_frame, text=group_name, padding=8)
            group.pack(fill="x", pady=(0, 8))
            for index, (label, command) in enumerate(commands):
                button = ttk.Button(group, text=label, command=lambda c=command: self._click_command(c))
                button.grid(row=index // 2, column=index % 2, sticky="ew", padx=4, pady=4, ipady=5)
            group.columnconfigure(0, weight=1)
            group.columnconfigure(1, weight=1)
        ttk.Label(outer, text="Кнопки запускают те же действия, что и голосовые команды. "
                              "Для поиска и напоминаний появится поле ввода.",
                  wraplength=840).pack(anchor="w")

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
        if command == "перезагрузи компьютер":
            if not messagebox.askyesno("Подтвердите перезагрузку", "Перезагрузить компьютер сейчас?", parent=self.root):
                return
        if command == "очисти корзину":
            if not messagebox.askyesno("Подтвердите очистку", "Удалить содержимое корзины?", parent=self.root):
                return
        self.on_command(command)

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
