"""Modern light Tkinter interface for Zero Control."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from dialog_utils import activate_modal, center_window, apply_modern_style


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

    def __init__(self, on_close, on_command, microphone_status="ПРОВЕРКА", on_open_mail=None, on_open_files=None, on_open_reminders=None, on_open_screen=None, on_open_other=None, on_open_notes=None, on_open_settings=None):
        self.root = tk.Tk()
        self.root.title("Zero Control")
        self.root.geometry("760x600")
        self.root.minsize(620, 500)
        self.root.configure(bg=self.BG)
        self.root.overrideredirect(True)
        self.on_close = on_close
        self.on_command = on_command
        self.on_open_mail = on_open_mail or (lambda: None)
        self.on_open_files = on_open_files or (lambda: None)
        self.on_open_reminders = on_open_reminders or (lambda: None)
        self.on_open_screen = on_open_screen or (lambda: None)
        self.on_open_other = on_open_other or (lambda: None)
        self.on_open_notes = on_open_notes or (lambda: None)
        self.on_open_settings = on_open_settings or (lambda: None)
        self.microphone_var = tk.StringVar(value=microphone_status)
        self.listening_var = tk.StringVar(value="ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
        self._recording_overlay = None
        self._busy_overlay = None
        self._build()
        self._prepare_recording_overlay()
        center_window(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._tray_icon = None
        self._install_drag_bindings(self._content_frame)
        self._set_application_icon()
        self.root.update_idletasks()
        self._apply_windows_taskbar_style()
        self.root.after(250, self._apply_windows_taskbar_style)
        self._start_tray_icon()

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
        style.configure("Title.TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10, "bold"))
        style.configure("StatusTitle.TLabel", background=self.SURFACE, foreground=self.TEXT, font=("Segoe UI", 9, "bold"))
        style.configure("StatusValue.TLabel", background=self.SURFACE, foreground=self.TEXT, font=("Segoe UI", 9))
        style.configure("Action.TButton", background=self.SURFACE, foreground=self.TEXT,
                        bordercolor=self.BORDER, lightcolor=self.BORDER, darkcolor=self.BORDER,
                        relief="solid", borderwidth=1, padding=(8, 7),
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
                        padding=(11, 6), font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", self.SURFACE), ("active", "#E0E3F0")],
                  foreground=[("selected", self.ACCENT), ("active", self.TEXT)])

    def _build(self):
        self._build_styles()
        outer = ttk.Frame(self.root, padding=(15, 11, 15, 9))
        outer.pack(fill="both", expand=True)
        self._content_frame = outer

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        header.bind("<ButtonPress-1>", self._start_window_drag)
        header.bind("<B1-Motion>", self._drag_window)
        brand = ttk.Frame(header)
        brand.pack(side="left", fill="x", expand=True)
        ttk.Label(brand, text="Zero Control", font=("Segoe UI", 11, "bold"),
                  foreground=self.ACCENT).pack(anchor="w")
        controls = ttk.Frame(header)
        controls.pack(side="right", anchor="n")
        ttk.Button(controls, text="🔧", style="Header.TButton",
                   command=self.on_open_settings).pack(side="left", padx=2)
        ttk.Button(controls, text="—", style="Header.TButton",
                   command=self.root.iconify).pack(side="left", padx=2)
        ttk.Button(controls, text="✕", style="Header.TButton",
                   command=self.close).pack(side="left", padx=2)

        status_card = tk.Frame(outer, bg=self.SURFACE, highlightthickness=1,
                               highlightbackground=self.BORDER, bd=0)
        status_card.pack(fill="x", pady=(0, 11))
        status_inner = tk.Frame(status_card, bg=self.SURFACE, padx=11, pady=8)
        status_inner.pack(fill="x")
        left = tk.Frame(status_inner, bg=self.SURFACE)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="СОСТОЯНИЕ", bg=self.SURFACE, fg=self.MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
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

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 20))
        cards = [
            ("✉", "Почта", "Письма и отправка файлов", self.on_open_mail),
            ("▤", "Файлы", "Поиск и рабочие папки", self.on_open_files),
            ("▤", "Заметки и дела", "Заметки, задачи и сроки", self.on_open_reminders),
            ("▣", "Экран", "Снимок и анализ экрана", self.on_open_screen),
            ("◉", "Камера", "Просмотр видеопотока", self.on_open_other),
            ("▧", "Фото-заметки", "Текст, фото и файлы", self.on_open_notes),
        ]
        for col, (symbol, title, hint, callback) in enumerate(cards):
            card = tk.Frame(actions, bg=self.SURFACE, highlightthickness=1,
                            highlightbackground=self.BORDER, bd=0, cursor="hand2")
            card.grid(row=0, column=col, sticky="nsew",
                      padx=(0 if col == 0 else 3, 0 if col == len(cards) - 1 else 3))
            actions.columnconfigure(col, weight=1, uniform="action")
            icon = tk.Label(card, text=symbol, bg=self.SURFACE, fg=self.ACCENT,
                            font=("Segoe UI Symbol", 12, "bold"))
            icon.pack(pady=(5, 1))
            name = tk.Label(card, text=title, bg=self.SURFACE, fg=self.TEXT,
                            font=("Segoe UI", 8, "bold"), wraplength=92,
                            justify="center", height=2)
            name.pack(fill="x", padx=2, pady=(0, 5))
            for widget in (card, icon, name):
                widget.bind("<Button-1>", lambda _e, fn=callback: fn())
                widget.bind("<Enter>", lambda _e, c=card, ws=(icon, name): self._hover_card(c, ws, True))
                widget.bind("<Leave>", lambda _e, c=card, ws=(icon, name): self._hover_card(c, ws, False))

        ttk.Label(outer, text="Команды", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        command_area = tk.Frame(outer, bg=self.SURFACE, highlightthickness=1,
                                highlightbackground=self.BORDER, bd=0)
        command_area.pack(fill="both", expand=True)
        command_canvas = tk.Canvas(command_area, bg=self.SURFACE, highlightthickness=0, bd=0)
        command_scroll = ttk.Scrollbar(command_area, orient="vertical", command=command_canvas.yview)
        command_canvas.configure(yscrollcommand=command_scroll.set)
        command_scroll.pack(side="right", fill="y")
        command_canvas.pack(side="left", fill="both", expand=True)
        command_list = tk.Frame(command_canvas, bg=self.SURFACE)
        list_window = command_canvas.create_window((0, 0), window=command_list, anchor="nw")

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
        for index, (title, description, phrase) in enumerate(commands):
            row = tk.Frame(command_list, bg=self.SURFACE, padx=10, pady=4)
            row.pack(fill="x")
            tk.Label(row, text=title, bg=self.SURFACE, fg=self.TEXT,
                     font=("Segoe UI", 9, "bold"), anchor="w", width=27).pack(side="left")
            tk.Label(row, text=description, bg=self.SURFACE, fg=self.MUTED,
                     font=("Segoe UI", 8), anchor="w").pack(side="left", fill="x", expand=True, padx=(7, 10))
            tk.Label(row, text="«" + phrase + "»", bg=self.SURFACE, fg=self.ACCENT,
                     font=("Segoe UI", 8), anchor="e").pack(side="right")
            if index < len(commands) - 1:
                tk.Frame(command_list, bg=self.BORDER, height=1).pack(fill="x", padx=10)

        def update_scroll_region(_event=None):
            command_canvas.configure(scrollregion=command_canvas.bbox("all"))
            command_canvas.itemconfigure(list_window, width=command_canvas.winfo_width())

        command_list.bind("<Configure>", update_scroll_region)
        command_canvas.bind("<Configure>", update_scroll_region)
        command_canvas.bind("<Enter>", lambda _e: command_canvas.bind_all(
            "<MouseWheel>", lambda e: command_canvas.yview_scroll(int(-e.delta / 120), "units")))
        command_canvas.bind("<Leave>", lambda _e: command_canvas.unbind_all("<MouseWheel>"))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(7, 0))
        ttk.Label(footer, text="Right Ctrl — голосовая команда   ·   Right Ctrl + Right Shift — диктовка",
                  style="Muted.TLabel").pack(anchor="center")

    def _install_drag_bindings(self, root_widget):
        """Allow dragging from non-interactive surfaces of the frameless window."""
        interactive = {"Button", "TButton", "Entry", "TEntry", "Text", "Canvas",
                       "Scrollbar", "TScrollbar", "Treeview", "TCombobox", "Combobox"}
        def visit(widget):
            try:
                if widget is not root_widget and widget.winfo_class() in interactive:
                    return
                if str(widget.cget("cursor") or "") == "hand2":
                    return
                if widget.winfo_class() in {"Frame", "TFrame", "Label", "TLabel"}:
                    widget.bind("<ButtonPress-1>", self._start_window_drag, add="+")
                    widget.bind("<B1-Motion>", self._drag_window, add="+")
                for child in widget.winfo_children():
                    visit(child)
            except (tk.TclError, AttributeError):
                return
        visit(root_widget)

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

    def _apply_windows_taskbar_style(self):
        """Expose a frameless Tk window as a normal Windows taskbar application."""
        if __import__("sys").platform != "win32":
            return
        try:
            import ctypes
            hwnd = self.root.winfo_id()
            user32 = ctypes.windll.user32
            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_long.restype = ctypes.c_ssize_t
            get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
            set_long.restype = ctypes.c_ssize_t
            set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            style = get_long(hwnd, -20)
            style = (style & ~0x00000080) | 0x00040000
            set_long(hwnd, -20, style)
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_uint,
            ]
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x2 | 0x1 | 0x4 | 0x20)
        except Exception as exc:
            print(f"[GUI] Не удалось включить кнопку на панели задач: {exc}", flush=True)

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
            self._apply_windows_taskbar_style()
        except tk.TclError:
            pass

    def _tray_exit(self, icon=None, item=None):
        try:
            self.root.after(0, self.close)
        except tk.TclError:
            pass

    def _start_window_drag(self, event):
        self._drag_offset_x = event.x_root - self.root.winfo_x()
        self._drag_offset_y = event.y_root - self.root.winfo_y()

    def _drag_window(self, event):
        x = event.x_root - getattr(self, "_drag_offset_x", 0)
        y = event.y_root - getattr(self, "_drag_offset_y", 0)
        self.root.geometry(f"+{x}+{y}")

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
