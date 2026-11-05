"""Compact main Tkinter window with dropdown command groups."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from dialog_utils import activate_modal, center_window


class AssistantWindow:
    def __init__(self, on_close, on_command, microphone_status="ПРОВЕРКА", on_open_mail=None, on_open_files=None, on_open_reminders=None, on_open_screen=None):
        self.root = tk.Tk()
        self.root.title("GigaAM — голосовой помощник")
        self.root.geometry("900x620")
        self.root.minsize(620, 480)
        self.on_close = on_close
        self.on_command = on_command
        self.on_open_mail = on_open_mail or (lambda: None)
        self.on_open_files = on_open_files or (lambda: None)
        self.on_open_reminders = on_open_reminders or (lambda: None)
        self.on_open_screen = on_open_screen or (lambda: None)
        self.microphone_var = tk.StringVar(value=microphone_status)
        self.listening_var = tk.StringVar(value="ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
        self._recording_overlay = None
        self._busy_overlay = None
        self._build()
        center_window(self.root)
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
        ttk.Button(smart_row, text="👥 Контакты", command=lambda: self.on_command("открой контакты")).pack(side="left", padx=4)
        ttk.Button(smart_row, text="✉ Почта", command=self.on_open_mail).pack(side="left", padx=4)
        ttk.Button(smart_row, text="📁 Файлы", command=self.on_open_files).pack(side="left", padx=4)
        ttk.Button(smart_row, text="🔔 Напоминания", command=self.on_open_reminders).pack(side="left", padx=4)
        ttk.Button(smart_row, text="🖼 Экран", command=self.on_open_screen).pack(side="left", padx=4)
        ttk.Button(smart_row, text="⚙ Настройки", command=lambda: self.on_command("открой настройки помощника")).pack(side="left", padx=4)
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(0, 8))
        groups = [
            ("🪟 Windows ▾", [("🔒 Заблокировать компьютер", "заблокируй компьютер"), ("🔄 Перезагрузить компьютер", "перезагрузи компьютер"), ("⬇ Открыть загрузки", "открой загрузки"), ("🗑 Открыть корзину", "открой корзину"), ("⚙ Открыть настройки", "открой настройки"), ("🧹 Очистить корзину", "очисти корзину"), ("📸 Сделать скриншот", "сделай скриншот")]),
            ("📁 Файлы ▾", [("🔎 Найти файл", "найди файл"), ("🗂 Разобрать папку", "разбери папку"), ("📝 Открыть Блокнот", "открой блокнот"), ("🧮 Открыть Калькулятор", "открой калькулятор"), ("📄 Открыть Word", "открой ворд"), ("📊 Открыть Excel", "открой эксель"), ("🌐 Открыть браузер", "открой браузер"), ("🖼 Открыть Изображения", "открой изображения"), ("📋 Вставить таблицу в Excel", "перенеси в excel"), ("🗒 Сохранить как заметку", "сохрани как заметку")]),
            ("🌐 Интернет ▾", [("🔎 Поиск в интернете", "найди в интернете"), ("📅 Создать напоминание", "напомни")]),
            ("✉ Почта ▾", [("👥 Мои контакты", "открой контакты"), ("➕ Добавить в контакты", "добавь в контакты"), ("✉ Новое письмо", "создай письмо"), ("📨 Прочитать новые письма", "прочитай новые письма"), ("📎 Отправить файлы на почту", "отправить файлы на почту")]),
        ]
        for label, commands in groups:
            button = ttk.Menubutton(row, text=label)
            menu = tk.Menu(button, tearoff=False)
            for title, command in commands:
                menu.add_command(label=title, command=lambda c=command: self._click_command(c))
            button["menu"] = menu
            button.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Label(outer, text="Команды доступны голосом и через меню.").pack(anchor="w")

    def _ask_ai(self):
        value = simpledialog.askstring("Спросить ИИ", "Что хочешь спросить у подключённого ИИ?", parent=self.root)
        if value and value.strip():
            self.on_command("спроси ИИ: " + value.strip())

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
            value = simpledialog.askstring("🔎 Поиск в интернете", "Что найти в интернете?", parent=self.root)
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

    def set_busy_overlay(self, message=None):
        """Показывает компактный индикатор ожидания справа по центру экрана."""
        def apply():
            if message:
                if self._busy_overlay is None or not self._busy_overlay.winfo_exists():
                    overlay = tk.Toplevel(self.root)
                    overlay.overrideredirect(True)
                    overlay.attributes("-topmost", True)
                    overlay.attributes("-alpha", 0.96)
                    overlay.configure(bg="#202124")
                    frame = tk.Frame(overlay, bg="#202124", padx=16, pady=10)
                    frame.pack()
                    tk.Label(frame, text="⏳", font=("Segoe UI Emoji", 22), fg="#fbbc04", bg="#202124").pack(side="left", padx=(0, 9))
                    self._busy_label = tk.Label(frame, text="", font=("Segoe UI", 10, "bold"), fg="white", bg="#202124")
                    self._busy_label.pack(side="left")
                    self._busy_overlay = overlay
                self._busy_label.configure(text=str(message))
                self._busy_overlay.update_idletasks()
                w = self._busy_overlay.winfo_reqwidth()
                h = self._busy_overlay.winfo_reqheight()
                x = self.root.winfo_screenwidth() - w - 24
                y = (self.root.winfo_screenheight() - h) // 2
                self._busy_overlay.geometry("+" + str(x) + "+" + str(y))
                self._busy_overlay.deiconify()
                self._busy_overlay.lift()
            elif self._busy_overlay is not None:
                self._busy_overlay.destroy()
                self._busy_overlay = None
                self._busy_label = None
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


def show_ai_answer(parent, question, answer=None, error=None):
    """Показывает ответ подключённой модели в отдельном окне Tkinter."""
    window = tk.Toplevel(parent)
    window.title("Ответ подключённого ИИ")
    window.geometry("720x560")
    window.minsize(480, 320)
    frame = ttk.Frame(window, padding=14)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Твой вопрос", font=("Segoe UI", 11, "bold")).pack(anchor="w")
    question_box = tk.Text(frame, height=4, wrap="word", font=("Segoe UI", 10))
    question_box.pack(fill="x", pady=(5, 12))
    question_box.insert("1.0", question)
    question_box.configure(state="disabled")
    ttk.Label(frame, text="Ответ ИИ" if not error else "Не удалось получить ответ",
              font=("Segoe UI", 11, "bold")).pack(anchor="w")
    answer_box = tk.Text(frame, wrap="word", font=("Segoe UI", 10))
    answer_box.pack(fill="both", expand=True, pady=(5, 10))
    answer_box.insert("1.0", answer if answer else (error or "Пустой ответ"))
    answer_box.configure(state="disabled")
    ttk.Button(frame, text="Закрыть", command=window.destroy).pack(anchor="e")
    activate_modal(window, parent)
