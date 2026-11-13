"""Modern light Tkinter interface for Zero Control."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from dialog_utils import activate_modal, center_window, apply_modern_style


class AssistantWindow:
    BG = "#F7F8FA"
    SURFACE = "#FFFFFF"
    TEXT = "#202938"
    MUTED = "#697586"
    ACCENT = "#405E9B"
    ACCENT_HOVER = "#334D82"
    BORDER = "#E5E8ED"
    GREEN = "#25845B"
    RED = "#C34D4D"
    GREY = "#98A2B3"

    def __init__(self, on_close, on_command, microphone_status="ПРОВЕРКА", on_open_mail=None, on_open_files=None, on_open_reminders=None, on_open_screen=None, on_open_other=None, on_open_notes=None, on_open_settings=None, on_office_command=None):
        self.root = tk.Tk()
        self.root.title("Zero Control")
        self.root.geometry("820x700")
        self.root.minsize(680, 580)
        self.root.configure(bg=self.BG)
        self.on_close = on_close
        self.on_command = on_command
        self.on_open_mail = on_open_mail or (lambda: None)
        self.on_open_files = on_open_files or (lambda: None)
        self.on_open_reminders = on_open_reminders or (lambda: None)
        self.on_open_screen = on_open_screen or (lambda: None)
        self.on_open_other = on_open_other or (lambda: None)
        self.on_open_notes = on_open_notes or (lambda: None)
        self.on_open_settings = on_open_settings or (lambda: None)
        self.on_office_command = on_office_command or (lambda command: None)
        self.microphone_var = tk.StringVar(value=microphone_status)
        self.listening_var = tk.StringVar(value="ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
        self._recording_overlay = None
        self._busy_overlay = None
        self._build()
        self._prepare_recording_overlay()
        center_window(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._tray_icon = None
        self._set_application_icon()
        self._start_tray_icon()

    def _build_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=self.BG)
        style.configure(
            "TLabel", background=self.BG, foreground=self.TEXT,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Muted.TLabel", background=self.BG, foreground=self.MUTED,
            font=("Segoe UI", 8),
        )
        style.configure(
            "Section.TLabel", background=self.BG, foreground=self.TEXT,
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "StatusValue.TLabel", background=self.SURFACE,
            foreground=self.TEXT, font=("Segoe UI", 9),
        )
        style.configure(
            "Quiet.TButton", background=self.SURFACE, foreground=self.TEXT,
            bordercolor=self.BORDER, padding=(11, 7),
            font=("Segoe UI", 9),
        )
        style.map(
            "Quiet.TButton",
            background=[("active", "#F0F2F5"), ("pressed", "#E8EBF0")],
            foreground=[("active", self.ACCENT)],
        )
        style.configure(
            "Accent.TButton", background=self.ACCENT, foreground="#FFFFFF",
            borderwidth=0, padding=(13, 8), font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", self.ACCENT_HOVER), ("pressed", self.ACCENT_HOVER)],
        )
        style.configure(
            "Search.TEntry", padding=(8, 6), fieldbackground=self.SURFACE,
            foreground=self.TEXT, bordercolor=self.BORDER,
            font=("Segoe UI", 9),
        )
    def _build(self):
        self._build_styles()
        outer = ttk.Frame(self.root, padding=(22, 18, 22, 14))
        outer.pack(fill="both", expand=True)
        self._content_frame = outer

        # Header: restrained branding and a clearly separated settings action.
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 18))
        brand = ttk.Frame(header)
        brand.pack(side="left", fill="x", expand=True)
        ttk.Label(
            brand, text="ZERO CONTROL", font=("Segoe UI", 12, "bold"),
            foreground=self.TEXT,
        ).pack(anchor="w")
        ttk.Label(
            brand, text="Персональный помощник", style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        settings_button = ttk.Button(
            header, text="Настройки", command=self.on_open_settings,
            style="Quiet.TButton",
        )
        settings_button.pack(side="right", anchor="center")

        # A compact system status panel; status variables are kept intact.
        status_card = tk.Frame(
            outer, bg=self.SURFACE, highlightthickness=1,
            highlightbackground=self.BORDER, bd=0,
        )
        status_card.pack(fill="x", pady=(0, 16))
        status_inner = tk.Frame(status_card, bg=self.SURFACE, padx=15, pady=11)
        status_inner.pack(fill="x")
        tk.Label(
            status_inner, text="СОСТОЯНИЕ СИСТЕМЫ", bg=self.SURFACE,
            fg=self.MUTED, font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(0, 7))
        details = tk.Frame(status_inner, bg=self.SURFACE)
        details.pack(fill="x")
        mic_group = tk.Frame(details, bg=self.SURFACE)
        mic_group.pack(side="left", padx=(0, 24))
        self.mic_dot = tk.Canvas(
            mic_group, width=10, height=10, bg=self.SURFACE,
            highlightthickness=0, bd=0,
        )
        self.mic_dot.pack(side="left", padx=(0, 7))
        self.mic_dot_id = self.mic_dot.create_oval(
            1, 1, 9, 9, fill=self.GREY, outline="",
        )
        tk.Label(
            mic_group, text="Микрофон", bg=self.SURFACE, fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left")
        ttk.Label(
            mic_group, textvariable=self.microphone_var,
            style="StatusValue.TLabel",
        ).pack(side="left", padx=(7, 0))

        command_group = tk.Frame(details, bg=self.SURFACE)
        command_group.pack(side="left")
        self.state_dot = tk.Canvas(
            command_group, width=10, height=10, bg=self.SURFACE,
            highlightthickness=0, bd=0,
        )
        self.state_dot.pack(side="left", padx=(0, 7))
        self.state_dot_id = self.state_dot.create_oval(
            1, 1, 9, 9, fill=self.GREY, outline="",
        )
        tk.Label(
            command_group, text="Голосовое управление", bg=self.SURFACE,
            fg=self.MUTED, font=("Segoe UI", 9),
        ).pack(side="left")
        ttk.Label(
            command_group, textvariable=self.listening_var,
            style="StatusValue.TLabel",
        ).pack(side="left", padx=(7, 0))
        self._refresh_status_dots()

        # Welcome panel explains the existing keyboard controls; it does not
        # introduce a new recording action or change the audio workflow.
        welcome = tk.Frame(
            outer, bg="#F0F3F8", highlightthickness=1,
            highlightbackground=self.BORDER, bd=0,
        )
        welcome.pack(fill="x", pady=(0, 17))
        welcome_inner = tk.Frame(welcome, bg="#F0F3F8", padx=17, pady=13)
        welcome_inner.pack(fill="x")
        tk.Label(
            welcome_inner, text="Добро пожаловать", bg="#F0F3F8",
            fg=self.TEXT, font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w")
        tk.Label(
            welcome_inner, text="Чем могу помочь сегодня?", bg="#F0F3F8",
            fg=self.MUTED, font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 9))
        shortcuts = tk.Frame(welcome_inner, bg="#F0F3F8")
        shortcuts.pack(fill="x")
        tk.Label(
            shortcuts, text="RIGHT CTRL", bg="#FFFFFF", fg=self.ACCENT,
            font=("Segoe UI", 8, "bold"), padx=8, pady=5,
        ).pack(side="left")
        tk.Label(
            shortcuts, text="Голосовая команда", bg="#F0F3F8",
            fg=self.TEXT, font=("Segoe UI", 9),
        ).pack(side="left", padx=(8, 20))
        tk.Label(
            shortcuts, text="RIGHT CTRL + RIGHT SHIFT", bg="#FFFFFF",
            fg=self.ACCENT, font=("Segoe UI", 8, "bold"), padx=8, pady=5,
        ).pack(side="left")
        tk.Label(
            shortcuts, text="Диктовка", bg="#F0F3F8",
            fg=self.TEXT, font=("Segoe UI", 9),
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            outer, text="РАБОЧИЕ РАЗДЕЛЫ", style="Section.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 17))
        cards = [
            ("✉", "Почта", "Письма и отправка файлов", self.on_open_mail),
            ("▤", "Файлы", "Поиск и рабочие папки", self.on_open_files),
            ("▧", "Заметки и дела", "Задачи и сроки", self.on_open_reminders),
            ("▣", "Экран", "Снимок и анализ", self.on_open_screen),
            ("◉", "Камера", "Просмотр видеопотока", self.on_open_other),
            ("▧", "Фото-заметки", "Текст, фото и файлы", self.on_open_notes),
        ]
        for index, (symbol, title, hint, callback) in enumerate(cards):
            row_index, col_index = divmod(index, 3)
            card = tk.Frame(
                actions, bg=self.SURFACE, highlightthickness=1,
                highlightbackground=self.BORDER, bd=0, cursor="hand2",
            )
            card.grid(
                row=row_index, column=col_index, sticky="nsew",
                padx=(0 if col_index == 0 else 5, 0 if col_index == 2 else 5),
                pady=(0, 8),
            )
            actions.columnconfigure(col_index, weight=1, uniform="action")
            actions.rowconfigure(row_index, weight=1)
            icon = tk.Label(
                card, text=symbol, bg=self.SURFACE, fg=self.ACCENT,
                font=("Segoe UI Symbol", 17),
            )
            icon.pack(anchor="w", padx=13, pady=(10, 2))
            name = tk.Label(
                card, text=title, bg=self.SURFACE, fg=self.TEXT,
                font=("Segoe UI", 10, "bold"), anchor="w",
            )
            name.pack(fill="x", padx=13)
            description = tk.Label(
                card, text=hint, bg=self.SURFACE, fg=self.MUTED,
                font=("Segoe UI", 8), anchor="w",
            )
            description.pack(fill="x", padx=13, pady=(3, 11))
            widgets = (icon, name, description)
            for widget in (card,) + widgets:
                widget.bind("<Button-1>", lambda _event, fn=callback: fn())
                widget.bind(
                    "<Enter>",
                    lambda _event, c=card, ws=widgets: self._hover_card(c, ws, True),
                )
                widget.bind(
                    "<Leave>",
                    lambda _event, c=card, ws=widgets: self._hover_card(c, ws, False),
                )

        commands_header = ttk.Frame(outer)
        commands_header.pack(fill="x", pady=(0, 7))
        ttk.Label(
            commands_header, text="КОМАНДЫ ПОМОЩНИКА",
            style="Section.TLabel",
        ).pack(side="left")

        command_search = ttk.Entry(
            commands_header, textvariable=tk.StringVar(),
            style="Search.TEntry", width=28,
        )
        self.command_search_var = tk.StringVar()
        command_search.configure(textvariable=self.command_search_var)
        command_search.pack(side="right")
        command_search.insert(0, "")
        command_search.bind("<KeyRelease>", lambda _event: filter_commands())

        command_area = tk.Frame(
            outer, bg=self.SURFACE, highlightthickness=1,
            highlightbackground=self.BORDER, bd=0,
        )
        command_area.pack(fill="both", expand=True)
        command_canvas = tk.Canvas(
            command_area, bg=self.SURFACE, highlightthickness=0, bd=0,
        )
        command_scroll = ttk.Scrollbar(
            command_area, orient="vertical", command=command_canvas.yview,
        )
        command_canvas.configure(yscrollcommand=command_scroll.set)
        command_scroll.pack(side="right", fill="y")
        command_canvas.pack(side="left", fill="both", expand=True)
        command_list = tk.Frame(command_canvas, bg=self.SURFACE)
        list_window = command_canvas.create_window(
            (0, 0), window=command_list, anchor="nw",
        )

        commands = [
            ("Заблокировать компьютер", "Заблокирует текущий сеанс Windows.", "заблокируй компьютер"),
            ("Перезагрузить компьютер", "Перезапустит Windows после подтверждения.", "перезагрузи компьютер"),
            ("Открыть настройки Windows", "Откроет системные параметры Windows.", "открой настройки Windows"),
            ("Открыть папку Загрузки", "Покажет загруженные файлы.", "открой загрузки"),
            ("Сделать скриншот", "Сохранит снимок всех экранов.", "сделай скриншот"),
            ("Найти файл", "Найдёт файл или папку по названию.", "найди файл"),
            ("Разобрать папку", "Откроет предварительный просмотр сортировки файлов.", "разбери папку"),
            ("Открыть Блокнот", "Запустит стандартный текстовый редактор.", "открой блокнот"),
            ("Открыть Калькулятор", "Запустит калькулятор Windows.", "открой калькулятор"),
            ("Открыть Word", "Запустит Microsoft Word.", "открой Word"),
            ("Открыть Excel", "Запустит Microsoft Excel.", "открой Excel"),
            ("Открыть браузер", "Откроет браузер.", "открой браузер"),
            ("Открыть изображения", "Откроет системную папку изображений.", "открой изображения"),
            ("Перенести таблицу в Excel", "Создаст книгу из таблицы в буфере обмена.", "перенеси в Excel"),
            ("Сохранить текст как заметку", "Добавит скопированный текст в общие заметки и дела.", "сохрани как заметку"),
            ("Поиск в интернете", "Найдёт информацию в интернете.", "найди в интернете"),
            ("Создать запись", "Сохранит заметку или дело; можно добавить срок.", "запомни купить фильтр"),
            ("Создать напоминание", "Добавит срок к записи и озвучит его в нужное время.", "напомни завтра в 9 позвонить"),
            ("Отметить выполненным", "Закроет активную запись, сохранив её в истории.", "отметь фильтр выполненным"),
            ("Открыть заметки и дела", "Покажет заметки, задачи и напоминания вместе.", "открой заметки и дела"),
            ("Открыть почту", "Откроет почтовый клиент.", "открой почту"),
            ("Прочитать новые письма", "Проверит и кратко перескажет непрочитанные письма.", "прочитай новые письма"),
            ("Создать письмо", "Подготовит новое письмо.", "создай письмо"),
            ("Спросить ИИ", "Ответит на вопрос обычным текстом или голосом.", "спроси ИИ: твой вопрос"),
            ("Проанализировать экран", "Сделает снимок и объяснит, что на нём отображено.", "что у меня на экране"),
            ("Спросить о камере", "Получит свежий кадр и ответит по изображению.", "что видно на камере"),
        ]
        command_rows = []
        for title, description, phrase in commands:
            row = tk.Frame(command_list, bg=self.SURFACE, padx=12, pady=7)
            row.pack(fill="x")
            tk.Label(
                row, text=title, bg=self.SURFACE, fg=self.TEXT,
                font=("Segoe UI", 9, "bold"), anchor="w", width=27,
            ).pack(side="left")
            tk.Label(
                row, text=description, bg=self.SURFACE, fg=self.MUTED,
                font=("Segoe UI", 8), anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=(7, 10))
            tk.Label(
                row, text="«" + phrase + "»", bg=self.SURFACE, fg=self.ACCENT,
                font=("Segoe UI", 8), anchor="e",
            ).pack(side="right")
            separator = tk.Frame(command_list, bg=self.BORDER, height=1)
            separator.pack(fill="x", padx=12)
            command_rows.append((row, title, description, phrase, separator))

        def filter_commands():
            query = self.command_search_var.get().strip().casefold()
            for row, title, description, phrase, separator in command_rows:
                visible = not query or query in " ".join(
                    (title, description, phrase),
                ).casefold()
                if visible:
                    row.pack(fill="x")
                    separator.pack(fill="x", padx=12)
                else:
                    row.pack_forget()
                    separator.pack_forget()
            command_canvas.configure(scrollregion=command_canvas.bbox("all"))

        def update_scroll_region(_event=None):
            command_canvas.configure(scrollregion=command_canvas.bbox("all"))
            command_canvas.itemconfigure(
                list_window, width=command_canvas.winfo_width(),
            )

        command_list.bind("<Configure>", update_scroll_region)
        command_canvas.bind("<Configure>", update_scroll_region)
        command_canvas.bind(
            "<Enter>",
            lambda _event: command_canvas.bind_all(
                "<MouseWheel>",
                lambda event: command_canvas.yview_scroll(
                    int(-event.delta / 120), "units",
                ),
            ),
        )
        command_canvas.bind(
            "<Leave>", lambda _event: command_canvas.unbind_all("<MouseWheel>"),
        )

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(11, 0))
        ttk.Button(
            footer, text="ИИ-помощник Word / Excel",
            command=self._ask_office_command, style="Accent.TButton",
        ).pack(anchor="center", pady=(0, 5))
        ttk.Label(
            footer,
            text="Zero Control  ·  Right Ctrl — голосовая команда  ·  Right Ctrl + Right Shift — диктовка",
            style="Muted.TLabel",
        ).pack(anchor="center")

    def _ask_office_command(self):
        command = simpledialog.askstring(
            "ИИ-помощник Office",
            "Что нужно сделать в открытом Word или Excel?",
            parent=self.root,
        )
        if command and command.strip():
            self.on_office_command(command.strip())

    def _set_application_icon(self):
        """Set the application icon used by Tk and the notification area."""
        try:
            from PIL import Image, ImageDraw, ImageTk
            image = Image.new("RGBA", (64, 64), (81, 70, 216, 255))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((7, 7, 57, 57), radius=13, fill=(255, 255, 255, 255))
            draw.ellipse((20, 18, 44, 42), fill=(81, 70, 216, 255))
            draw.rounded_rectangle((28, 37, 36, 48), radius=3, fill=(81, 70, 216, 255))
            self._tray_image = image
            self._tk_icon = ImageTk.PhotoImage(image, master=self.root)
            self.root.iconphoto(True, self._tk_icon)
        except Exception as exc:
            self._tray_image = None
            print(f"[GUI] Не удалось установить иконку приложения: {exc}", flush=True)

    def _start_tray_icon(self):
        """Start a notification-area icon with restore and exit actions."""
        try:
            import pystray
            if self._tray_image is None:
                return
            menu = pystray.Menu(
                pystray.MenuItem("Открыть Zero Control", self._tray_restore, default=True),
                pystray.MenuItem("Выход", self._tray_exit),
            )
            self._tray_icon = pystray.Icon("zero_control", self._tray_image, "Zero Control", menu)
            self._tray_icon.run_detached()
        except Exception as exc:
            print(f"[GUI] Не удалось запустить значок в системном трее: {exc}", flush=True)

    def _tray_restore(self, icon=None, item=None):
        try:
            self.root.after(0, self._restore_from_tray)
        except tk.TclError:
            pass

    def _restore_from_tray(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def _tray_exit(self, icon=None, item=None):
        try:
            self.root.after(0, self.close)
        except tk.TclError:
            pass

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

    def _prepare_recording_overlay(self):
        """Создаёт компактный прямоугольный индикатор записи."""
        overlay = tk.Toplevel(self.root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.94)
        overlay.configure(bg="#202124")
        frame = tk.Frame(overlay, bg="#202124", padx=14, pady=6)
        frame.pack()
        tk.Label(frame, text="🎙", font=("Segoe UI Emoji", 34),
                 fg="#ff3b30", bg="#202124").pack()
        self._overlay_label = tk.Label(
            frame, text="", font=("Segoe UI", 9, "bold"),
            fg="white", bg="#202124"
        )
        self._overlay_label.pack(pady=(2, 0))
        overlay.update_idletasks()
        self._recording_overlay = overlay

    def set_recording_overlay(self, active, mode=None):
        def apply():
            if active:
                self._overlay_label.configure(
                    text="СЛУШАЮ" if mode == "command" else "ДИКТОВКА"
                )
                w = self._recording_overlay.winfo_reqwidth()
                h = self._recording_overlay.winfo_reqheight()
                x = (self.root.winfo_screenwidth() - w) // 2
                y = (self.root.winfo_screenheight() - h) // 2
                self._recording_overlay.geometry(f"+{x}+{y}")
                self._recording_overlay.deiconify()
                self._recording_overlay.lift()
            elif self._recording_overlay is not None:
                self._recording_overlay.withdraw()
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
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        self.on_close()
        self.root.destroy()


def show_ai_answer(parent, question, answer=None, error=None):
    """Показывает ответ подключённой модели в отдельном окне Tkinter."""
    window = tk.Toplevel(parent)
    apply_modern_style(window)
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
