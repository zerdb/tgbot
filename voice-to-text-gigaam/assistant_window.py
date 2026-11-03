
"""Main Tkinter help and live-status window."""
import tkinter as tk
from tkinter import ttk


class AssistantWindow:
    def __init__(self, on_close, microphone_status="ПРОВЕРКА"):
        self.root = tk.Tk()
        self.root.title("GigaAM — голосовой помощник")
        self.root.geometry("820x720")
        self.root.minsize(680, 560)
        self.on_close = on_close
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
        ttk.Label(outer, text="Как пользоваться", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        guide = (
            "1. Диктовка текста: зажмите Ctrl+Shift (левые Ctrl и Shift), произнесите текст и отпустите клавиши. "
            "Распознанный текст будет вставлен в активное поле.\n"
            "2. Голосовая команда: зажмите Right Ctrl, произнесите одну команду и отпустите клавишу. "
            "Дождитесь распознавания и выполнения.\n"
            "3. Во время записи держите клавишу нажатой; после отпускания запись автоматически обрабатывается.\n"
            "4. Для выхода закройте это окно."
        )
        ttk.Label(outer, text=guide, wraplength=760, justify="left").pack(anchor="w", pady=(5, 12))
        ttk.Label(outer, text="Список голосовых команд", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        frame = ttk.Frame(outer)
        frame.pack(fill="both", expand=True, pady=(5, 10))
        text = tk.Text(frame, wrap="word", height=18, font=("Segoe UI", 10), padx=8, pady=8)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        commands = [
            ("«Заблокируй компьютер» / «Заблокируй экран» / «Блокируй комп»", "Блокирует текущий сеанс Windows."),
            ("«Перезагрузи компьютер» / «Перезапусти ПК» / «Сделай перезагрузку»", "Перезагружает Windows."),
            ("«Покажи загрузки» / «Открой скачанное» / «Папка загрузки»", "Открывает папку «Загрузки»."),
            ("«Открой настройки» / «Параметры Windows» / «Настройки системы»", "Открывает системные настройки Windows."),
            ("«Очисти корзину» / «Опустоши корзину» / «Почисти корзину»", "Очищает корзину."),
            ("«Сделай скриншот» / «Сними экран» / «Сделай снимок»", "Сохраняет снимок всех экранов в папку «Скриншоты»."),
            ("«Напомни ...» / «Поставь напоминание ...» / «Создай напоминание ...»", "Создаёт напоминание. Например: «Напомни через 10 минут проверить духовку»."),
            ("«Найди в интернете ...» / «Поищи в сети ...» / «Загугли ...»", "Выполняет поиск в интернете по произнесённому запросу."),
            ("«Найди файл ...» / «Поищи файл ...» / «Найди документ ...»", "Ищет файлы на компьютере по названию или запросу."),
            ("«Отправь на почту» / «Скинь по почте» / «Пришли на email» / «Перешли на почту»", "Открывает окно письма. Скопированные в Проводнике файлы добавляются во вложения; тема формируется из имён файлов."),
            ("«Добавить контакт» / «Сохрани контакт» / «Запиши контакт»", "Открывает форму для добавления имени и адреса электронной почты."),
            ("«Покажи контакты» / «Мои контакты» / «Открой контакты»", "Показывает сохранённые контакты."),
            ("«Отмена»", "В окне письма отменяет отправку и закрывает форму без отправки."),
        ]
        for title, description in commands:
            text.insert("end", title + "\n", "title")
            text.insert("end", "   " + description + "\n\n")
        text.tag_configure("title", font=("Segoe UI", 10, "bold"))
        text.configure(state="disabled")
        ttk.Label(outer, text="Примечание: для диктовки удерживайте левый Ctrl+левый Shift; для команды произносите фразу после нажатия Right Ctrl и отпускайте клавишу только после окончания фразы.", wraplength=760).pack(anchor="w")
    
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
