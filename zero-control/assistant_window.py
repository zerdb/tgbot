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
        tk.Label(details, text="Режим", bg=self.SURFACE, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        ttk.Label(details, textvariable=self.listening_var, style="StatusValue.TLabel").pack(side="left", padx=(5, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 11))
        for text, command in (
            ("Почта", self.on_open_mail),
            ("Файлы", self.on_open_files),
            ("Напоминания", self.on_open_reminders),
            ("Экран", self.on_open_screen),
            ("Камера", self.on_open_other),
            ("Заметки", self.on_open_notes),
        ):
            ttk.Button(actions, text=text, style="Action.TButton", command=command).pack(
                side="left", fill="x", expand=True, padx=(0, 6)
            )

        ttk.Label(outer, text="Команды", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        command_area = tk.Frame(outer, bg=self.SURFACE, highlightthickness=1,
                                highlightbackground=self.BORDER, bd=0)
        command_area.pack(fill="both", expand=True)
        command_canvas = tk.Canvas(command_area, bg=self.SURFACE, highlightthickness=0)
        command_scroll = ttk.Scrollbar(command_area, orient="vertical", command=command_canvas.yview)
        command_list = tk.Frame(command_canvas, bg=self.SURFACE)
        list_window = command_canvas.create_window((0, 0), window=command_list, anchor="nw")
        command_canvas.configure(yscrollcommand=command_scroll.set)
        command_canvas.pack(side="left", fill="both", expand=True)
        command_scroll.pack(side="right", fill="y")

        commands = [
            ("Открыть блокнот", "Запустить приложение", "открой блокнот"),
            ("Открыть Excel", "Запустить приложение", "открой excel"),
            ("Найти файл", "Поиск по имени", "найди файл договор"),
            ("Напоминание", "Добавить в список дел", "напомни через 10 минут проверить почту"),
            ("Скриншот", "Снимок экрана", "сделай скриншот"),
            ("Заблокировать", "Блокировка Windows", "заблокируй компьютер"),
        ]
        for index, (title, description, phrase) in enumerate(commands):
            row = tk.Frame(command_list, bg=self.SURFACE, cursor="hand2")
            row.pack(fill="x", padx=10, pady=4)
            row.bind("<Button-1>", lambda e, p=phrase: self._click_command(p))
            for child_maker in (
                lambda: tk.Label(row, text=title, bg=self.SURFACE, fg=self.TEXT,
                                 font=("Segoe UI", 9, "bold"), anchor="w", width=27),
                lambda: tk.Label(row, text=description, bg=self.SURFACE, fg=self.MUTED,
                                 font=("Segoe UI", 8), anchor="w"),
                lambda: tk.Label(row, text="«" + phrase + "»", bg=self.SURFACE, fg=self.ACCENT,
                                 font=("Segoe UI", 8), anchor="e"),
            ):
                pass
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
        pass

    def _apply_windows_taskbar_style(self):
        pass

    def _start_tray_icon(self):
        pass

    def _tray_restore(self, icon=None, item=None):
        pass

    def _restore_from_tray(self):
        pass

    def _tray_exit(self, icon=None, item=None):
        pass

    def _start_window_drag(self, event):
        self._drag_offset_x = event.x_root - self.root.winfo_x()
        self._drag_offset_y = event.y_root - self.root.winfo_y()

    def _drag_window(self, event):
        x = event.x_root - getattr(self, "_drag_offset_x", 0)
        y = event.y_root - getattr(self, "_drag_offset_y", 0)
        self.root.geometry(f"+{x}+{y}")

    def _hover_card(self, card, widgets, active):
        pass

    def _refresh_status_dots(self):
        pass

    def _ask_ai(self):
        pass

    def _ask_smart_command(self):
        pass

    def _click_command(self, command):
        if callable(self.on_command):
            self.on_command(command)

    def _prepare_recording_overlay(self):
        pass

    def set_busy_overlay(self, text):
        pass

    def set_status(self, listening=None, microphone=None):
        if listening is not None:
            self.listening_var.set(listening)
        if microphone is not None:
            self.microphone_var.set(microphone)

    def run(self):
        self.root.mainloop()

    def close(self):
        self.on_close()
        self.root.destroy()


def show_ai_answer(parent, question, answer=None, error=None):
    window = tk.Toplevel(parent)
    apply_modern_style(window)
    window.title("Ответ подключённого ИИ")
    window.geometry("720x560")
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
