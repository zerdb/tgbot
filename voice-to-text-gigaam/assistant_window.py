"""Modern light Tkinter interface for the GigaAM voice assistant."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from dialog_utils import activate_modal, center_window


class AssistantWindow:
    BG = "#F4F6FB"
    SURFACE = "#FFFFFF"
    TEXT = "#172033"
    MUTED = "#7B8497"
    ACCENT = "#5146D8"
    ACCENT_HOVER = "#4338CA"
    BORDER = "#E6E9F2"
    GREEN = "#16A36A"
    RED = "#D9485F"
    GREY = "#98A2B3"

    def __init__(self, on_close, on_command, microphone_status="ПРОВЕРКА", on_open_mail=None, on_open_files=None, on_open_reminders=None, on_open_screen=None, on_open_other=None):
        self.root = tk.Tk()
        self.root.title("GigaAM — голосовой помощник")
        self.root.geometry("940x720")
        self.root.minsize(680, 600)
        self.root.configure(bg=self.BG)
        self.on_close = on_close
        self.on_command = on_command
        self.on_open_mail = on_open_mail or (lambda: None)
        self.on_open_files = on_open_files or (lambda: None)
        self.on_open_reminders = on_open_reminders or (lambda: None)
        self.on_open_screen = on_open_screen or (lambda: None)
        self.on_open_other = on_open_other or (lambda: None)
        self.microphone_var = tk.StringVar(value=microphone_status)
        self.listening_var = tk.StringVar(value="ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
        self._recording_overlay = None
        self._busy_overlay = None
        self._build()
        center_window(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=self.BG)
        style.configure("Surface.TFrame", background=self.SURFACE)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=self.SURFACE, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 23, "bold"))
        style.configure("Subtitle.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 12, "bold"))
        style.configure("StatusTitle.TLabel", background=self.SURFACE, foreground=self.TEXT, font=("Segoe UI", 9, "bold"))
        style.configure("StatusValue.TLabel", background=self.SURFACE, foreground=self.TEXT, font=("Segoe UI", 9))
        style.configure("Action.TButton", background=self.SURFACE, foreground=self.TEXT,
                        bordercolor=self.BORDER, lightcolor=self.BORDER, darkcolor=self.BORDER,
                        relief="solid", borderwidth=1, padding=(12, 15),
                        font=("Segoe UI", 10, "bold"))
        style.map("Action.TButton",
                  background=[("active", "#F0EFFF"), ("pressed", "#E8E6FF")],
                  foreground=[("active", self.ACCENT)])
        style.configure("Accent.TButton", background=self.ACCENT, foreground="#FFFFFF",
                        borderwidth=0, padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton", background=[("active", self.ACCENT_HOVER), ("pressed", self.ACCENT_HOVER)])
        style.configure("Header.TButton", background=self.BG, foreground=self.TEXT,
                        borderwidth=0, padding=(9, 7), font=("Segoe UI", 11, "bold"))
        style.map("Header.TButton", background=[("active", "#E9EAF5")])
        style.configure("TNotebook", background=self.BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background="#E9ECF4", foreground=self.MUTED,
                        padding=(16, 9), font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", self.SURFACE), ("active", "#E0E3F0")],
                  foreground=[("selected", self.ACCENT), ("active", self.TEXT)])

    def _build(self):
        self._build_styles()
        outer = ttk.Frame(self.root, padding=(24, 18, 24, 14))
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 18))
        brand = ttk.Frame(header)
        brand.pack(side="left", fill="x", expand=True)
        ttk.Label(brand, text="GigaAM", font=("Segoe UI", 11, "bold"),
                  foreground=self.ACCENT).pack(anchor="w")
        ttk.Label(brand, text="Голосовой помощник", style="Title.TLabel").pack(anchor="w", pady=(1, 0))
        ttk.Label(brand, text="Ваш помощник для голоса, файлов и повседневных задач",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))
        controls = ttk.Frame(header)
        controls.pack(side="right", anchor="n")
        ttk.Button(controls, text="⚙", style="Header.TButton",
                   command=lambda: self.on_command("открой настройки помощника")).pack(side="left", padx=2)
        ttk.Button(controls, text="—", style="Header.TButton",
                   command=self.root.iconify).pack(side="left", padx=2)
        ttk.Button(controls, text="✕", style="Header.TButton",
                   command=self.close).pack(side="left", padx=2)

        status_card = tk.Frame(outer, bg=self.SURFACE, highlightthickness=1,
                               highlightbackground=self.BORDER, bd=0)
        status_card.pack(fill="x", pady=(0, 20))
        status_inner = tk.Frame(status_card, bg=self.SURFACE, padx=16, pady=13)
        status_inner.pack(fill="x")
        left = tk.Frame(status_inner, bg=self.SURFACE)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="СОСТОЯНИЕ СИСТЕМЫ", bg=self.SURFACE, fg=self.MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 7))
        details = tk.Frame(left, bg=self.SURFACE)
        details.pack(anchor="w")
        self.mic_dot = tk.Canvas(details, width=10, height=10, bg=self.SURFACE,
                                 highlightthickness=0)
        self.mic_dot.pack(side="left", padx=(0, 6))
        self.mic_dot_id = self.mic_dot.create_oval(1, 1, 9, 9, fill=self.GREY, outline="")
        tk.Label(details, text="Микрофон", bg=self.SURFACE, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        ttk.Label(details, textvariable=self.microphone_var, style="StatusValue.TLabel").pack(side="left", padx=(5, 22))
        self.state_dot = tk.Canvas(details, width=10, height=10, bg=self.SURFACE,
                                   highlightthickness=0)
        self.state_dot.pack(side="left", padx=(0, 6))
        self.state_dot_id = self.state_dot.create_oval(1, 1, 9, 9, fill=self.GREY, outline="")
        tk.Label(details, text="Команды", bg=self.SURFACE, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        ttk.Label(details, textvariable=self.listening_var, style="StatusValue.TLabel").pack(side="left", padx=(5, 0))
        self._refresh_status_dots()

        ttk.Label(outer, text="Быстрые действия", style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 20))
        cards = [
            ("✉", "Почта", "Письма и отправка файлов", self.on_open_mail),
            ("▤", "Файлы", "Поиск и рабочие папки", self.on_open_files),
            ("◷", "Напоминания", "Планы и напоминания", self.on_open_reminders),
            ("▣", "Экран", "Снимок и анализ экрана", self.on_open_screen),
            ("◉", "Камера", "Просмотр видеопотока", self.on_open_other),
        ]
        for col, (symbol, title, hint, callback) in enumerate(cards):
            card = tk.Frame(actions, bg=self.SURFACE, highlightthickness=1,
                            highlightbackground=self.BORDER, bd=0, cursor="hand2")
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 5, 0 if col == 4 else 5))
            actions.columnconfigure(col, weight=1, uniform="action")
            icon = tk.Label(card, text=symbol, bg=self.SURFACE, fg=self.ACCENT,
                            font=("Segoe UI Symbol", 21, "bold"))
            icon.pack(anchor="w", padx=13, pady=(12, 3))
            name = tk.Label(card, text=title, bg=self.SURFACE, fg=self.TEXT,
                            font=("Segoe UI", 10, "bold"))
            name.pack(anchor="w", padx=13)
            desc = tk.Label(card, text=hint, bg=self.SURFACE, fg=self.MUTED,
                            font=("Segoe UI", 8), wraplength=125, justify="left")
            desc.pack(anchor="w", padx=13, pady=(3, 12))
            for widget in (card, icon, name, desc):
                widget.bind("<Button-1>", lambda _e, fn=callback: fn())
                widget.bind("<Enter>", lambda _e, c=card, ws=(icon, name, desc): self._hover_card(c, ws, True))
                widget.bind("<Leave>", lambda _e, c=card, ws=(icon, name, desc): self._hover_card(c, ws, False))

        ttk.Label(outer, text="Команды по категориям", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        groups = [
            ("Windows", [("🔒  Заблокировать компьютер", "заблокируй компьютер"), ("↻  Перезагрузить компьютер", "перезагрузи компьютер"), ("⬇  Открыть загрузки", "открой загрузки"), ("▧  Открыть корзину", "открой корзину"), ("⚙  Открыть настройки", "открой настройки"), ("♲  Очистить корзину", "очисти корзину"), ("▣  Сделать скриншот", "сделай скриншот")]),
            ("Файлы", [("⌕  Найти файл", "найди файл"), ("▤  Разобрать папку", "разбери папку"), ("▣  Открыть Блокнот", "открой блокнот"), ("▦  Открыть Калькулятор", "открой калькулятор"), ("▤  Открыть Word", "открой ворд"), ("▦  Открыть Excel", "открой эксель"), ("◎  Открыть браузер", "открой браузер"), ("▧  Открыть Изображения", "открой изображения"), ("▦  Вставить таблицу в Excel", "перенеси в excel"), ("✎  Сохранить как заметку", "сохрани как заметку")]),
            ("Интернет", [("⌕  Поиск в интернете", "найди в интернете"), ("◷  Создать напоминание", "напомни")]),
            ("Почта", [("➤  Отправить файлы на почту", "отправить файлы на почту")]),
            ("Камера", [("◉  Проверить белую машину", "проверь белую машину на камере")]),
        ]
        for tab_name, commands in groups:
            page = tk.Frame(notebook, bg=self.SURFACE, padx=14, pady=14)
            notebook.add(page, text=tab_name)
            for index, (label, command) in enumerate(commands):
                button = ttk.Button(page, text=label, style="Action.TButton",
                                    command=lambda c=command: self._click_command(c))
                button.grid(row=index // 2, column=index % 2, sticky="ew", padx=5, pady=5)
            page.columnconfigure(0, weight=1)
            page.columnconfigure(1, weight=1)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(13, 0))
        ttk.Label(footer, text="Right Ctrl — голосовая команда   ·   Right Ctrl + Right Shift — диктовка",
                  style="Muted.TLabel").pack(anchor="center")

    def _hover_card(self, card, widgets, active):
        bg = "#F2F1FF" if active else self.SURFACE
        border = "#C8C3FF" if active else self.BORDER
        try:
            card.configure(bg=bg, highlightbackground=border)
            for widget in widgets:
                widget.configure(bg=bg)
        except tk.TclError:
            pass

    def _refresh_status_dots(self):
        mic = self.microphone_var.get().upper()
        state = self.listening_var.get().upper()
        mic_color = self.GREEN if "НАЙДЕН" in mic else self.RED if "НЕ НАЙДЕН" in mic or "ОШИБ" in mic else self.GREY
        state_color = self.GREEN if "СЛУШАЮ" in state or "ДИКТОВКА" in state else self.RED if "ОШИБ" in state else self.ACCENT if "РАСПОЗНА" in state else self.GREY
        self.mic_dot.itemconfigure(self.mic_dot_id, fill=mic_color)
        self.state_dot.itemconfigure(self.state_dot_id, fill=state_color)

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
            self._refresh_status_dots()
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
