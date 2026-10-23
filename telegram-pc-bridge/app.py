import json
import os
import queue
import subprocess
import sys
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from telegram_client import TelegramBotClient

CONFIG = Path(__file__).with_name("config.json")


class TelegramBridgeApp:
    BG = "#F5F9FE"
    SIDEBAR = "#F8FBFF"
    CARD = "#FFFFFF"
    CARD_SOFT = "#F3F8FE"
    BORDER = "#DDE8F5"
    TEXT = "#17345F"
    MUTED = "#7087A5"
    BLUE = "#2878F0"
    BLUE_HOVER = "#1768DD"
    BLUE_SOFT = "#DDEEFF"
    GREEN = "#31C979"
    RED = "#E5484D"

    def __init__(self, root):
        self.root = root
        self.root.title("Telegram PC Bridge")
        self.root.geometry("1180x720")
        self.root.minsize(980, 620)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.client = None
        self.events = queue.Queue()
        config = self.load_config()
        self.token = ctk.StringVar(value=config.get("token", ""))
        self.allowed_user = ctk.StringVar(value=str(config.get("allowed_user_id", "")))
        self.status = ctk.StringVar(value="Остановлен")
        self.nav_buttons = {}
        self.pages = {}

        self.build_ui()
        self.show_page("Главная")
        self.root.after(100, self.process_events)
        self.root.after(350, self.auto_connect)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self):
        self.root.configure(fg_color=self.BG)

        self.sidebar = ctk.CTkFrame(
            self.root, width=205, corner_radius=0,
            fg_color=self.SIDEBAR, border_width=0,
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=16, pady=(20, 22))
        ctk.CTkLabel(
            brand, text="➤", width=38, height=38, corner_radius=19,
            fg_color="#2D9BF0", text_color="white",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left")
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(
            brand_text, text="Telegram PC Bridge", text_color=self.TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand_text, text="Удалённое управление ПК", text_color=self.MUTED,
            font=ctk.CTkFont(size=9),
        ).pack(anchor="w", pady=(1, 0))

        nav = [
            ("Главная", "⌂"),
            ("Настройки", "⚙"),
            ("Логи", "▤"),
            ("О программе", "ⓘ"),
        ]
        for name, icon in nav:
            button = ctk.CTkButton(
                self.sidebar,
                text=f"  {icon}   {name}",
                anchor="w",
                height=38,
                corner_radius=7,
                fg_color="transparent",
                hover_color="#E9F3FF",
                text_color=self.TEXT,
                font=ctk.CTkFont(size=12),
                command=lambda page=name: self.show_page(page),
            )
            button.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[name] = button

        ctk.CTkLabel(
            self.sidebar,
            text="v4  •  CustomTkinter",
            text_color="#9AAEC6",
            font=ctk.CTkFont(size=9),
        ).pack(side="bottom", anchor="w", padx=20, pady=16)

        self.content = ctk.CTkFrame(self.root, fg_color=self.BG, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

        header = ctk.CTkFrame(self.content, fg_color="transparent", height=68)
        header.pack(fill="x", padx=22, pady=(15, 5))
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="Telegram PC Bridge", text_color=self.TEXT,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Удалённое управление ПК через Telegram  •  Windows 11 UI",
            text_color=self.MUTED,
            font=ctk.CTkFont(size=10),
        ).pack(anchor="w", pady=(2, 0))

        self.page_host = ctk.CTkFrame(self.content, fg_color="transparent")
        self.page_host.pack(fill="both", expand=True, padx=22, pady=(0, 18))

        for page in ("Главная", "Настройки", "Логи", "О программе"):
            self.pages[page] = ctk.CTkFrame(self.page_host, fg_color="transparent")

        self.build_home()
        self.build_settings()
        self.build_logs()
        self.build_about()

    def card(self, parent):
        return ctk.CTkFrame(
            parent,
            fg_color=self.CARD,
            border_width=1,
            border_color=self.BORDER,
            corner_radius=10,
        )

    def section_title(self, parent, text, icon=""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(10, 5))
        ctk.CTkLabel(
            row, text=f"{icon}  {text}" if icon else text,
            text_color=self.TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="left")
        return row

    def build_home(self):
        page = self.pages["Главная"]

        connection = self.card(page)
        connection.pack(fill="x", pady=(0, 9))
        self.section_title(connection, "Подключение", "🔗")

        form = ctk.CTkFrame(connection, fg_color="transparent")
        form.pack(fill="x", padx=14, pady=(0, 12))
        form.grid_columnconfigure(0, weight=3)
        form.grid_columnconfigure(1, weight=2)

        token_box = ctk.CTkFrame(form, fg_color="transparent")
        token_box.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        ctk.CTkLabel(
            token_box, text="Bot Token", text_color=self.TEXT,
            font=ctk.CTkFont(size=9),
        ).pack(anchor="w", pady=(0, 3))
        ctk.CTkEntry(
            token_box, textvariable=self.token, show="•", height=31,
            corner_radius=6, fg_color="#F8FBFF",
            border_color="#BFD3EA", border_width=1,
            text_color=self.TEXT,
        ).pack(fill="x")

        user_box = ctk.CTkFrame(form, fg_color="transparent")
        user_box.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        ctk.CTkLabel(
            user_box, text="Telegram User ID", text_color=self.TEXT,
            font=ctk.CTkFont(size=9),
        ).pack(anchor="w", pady=(0, 3))
        ctk.CTkEntry(
            user_box, textvariable=self.allowed_user, height=31,
            corner_radius=6, fg_color="#F8FBFF",
            border_color="#BFD3EA", border_width=1,
            text_color=self.TEXT,
        ).pack(fill="x")

        self.connection_button = ctk.CTkButton(
            form, text="▶  Запустить", width=150, height=31,
            corner_radius=6, fg_color=self.BLUE, hover_color=self.BLUE_HOVER,
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self.toggle_connection,
        )
        self.connection_button.grid(row=0, column=2, sticky="s")

        cards = ctk.CTkFrame(page, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 9))
        cards.grid_columnconfigure((0, 1), weight=1)

        self.status_card = self.card(cards)
        self.status_card.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        status_inner = ctk.CTkFrame(self.status_card, fg_color="transparent")
        status_inner.pack(fill="x", padx=14, pady=11)
        self.status_dot = ctk.CTkLabel(
            status_inner, text="●", width=18,
            text_color="#94A3B8", font=ctk.CTkFont(size=17),
        )
        self.status_dot.pack(side="left")
        ctk.CTkLabel(
            status_inner, textvariable=self.status, text_color=self.TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="left", padx=(5, 0))
        ctk.CTkButton(
            status_inner, text="📂  Открыть файлы", width=128, height=28,
            corner_radius=7, fg_color="#EAF4FF", hover_color="#DDEEFF",
            text_color="#3471B9", font=ctk.CTkFont(size=9),
            command=self.open_downloads,
        ).pack(side="right")

        info = self.card(cards)
        info.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        info_inner = ctk.CTkFrame(info, fg_color="transparent")
        info_inner.pack(fill="x", padx=14, pady=9)
        ctk.CTkLabel(
            info_inner, text="🛡", width=22, text_color=self.BLUE,
            font=ctk.CTkFont(size=15),
        ).pack(side="left", padx=(0, 7))
        info_text = ctk.CTkFrame(info_inner, fg_color="transparent")
        info_text.pack(side="left")
        ctk.CTkLabel(
            info_text, text="Защищённый режим", text_color=self.TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            info_text,
            text="Allow-list команд • User ID • подтверждения опасных действий",
            text_color=self.MUTED, font=ctk.CTkFont(size=8),
        ).pack(anchor="w", pady=(2, 0))

        self.journal = self.card(page)
        self.journal.pack(fill="both", expand=True)
        top = self.section_title(self.journal, "Журнал активности", "▤")
        ctk.CTkButton(
            top, text="♲ Очистить", width=82, height=25,
            corner_radius=7, fg_color="#EAF4FF", hover_color="#DDEEFF",
            text_color="#3471B9", font=ctk.CTkFont(size=9),
            command=self.clear_messages,
        ).pack(side="right")

        self.messages = ctk.CTkTextbox(
            self.journal, corner_radius=8, border_width=0,
            fg_color=self.CARD_SOFT, text_color=self.TEXT,
            font=ctk.CTkFont(size=10),
        )
        self.messages.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.messages.configure(state="disabled")

        self.empty_hint = ctk.CTkLabel(
            self.messages,
            text="▱\nпока нет записей\nЗдесь будут отображаться история команд и действий",
            text_color="#8EA3BC",
            font=ctk.CTkFont(size=9),
            justify="center",
        )
        self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")

    def build_settings(self):
        page = self.pages["Настройки"]
        card = self.card(page)
        card.pack(fill="x")
        self.section_title(card, "Настройки Bridge", "⚙")
        ctk.CTkLabel(
            card,
            text="Основные параметры подключения находятся на главной странице.\n"
                 "После сохранения Bot Token и User ID Bridge подключается автоматически при следующем запуске.",
            justify="left", text_color=self.MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=16, pady=(4, 16))

    def build_logs(self):
        page = self.pages["Логи"]
        card = self.card(page)
        card.pack(fill="both", expand=True)
        self.section_title(card, "Локальный журнал", "▤")
        ctk.CTkLabel(
            card,
            text="Оперативный журнал отображается на главной. Полный аудит хранится локально в audit.log.",
            text_color=self.MUTED, font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=16, pady=(4, 8))
        ctk.CTkButton(
            card, text="📂 Открыть папку Bridge", width=160,
            fg_color="#EAF4FF", hover_color="#DDEEFF", text_color="#3471B9",
            command=self.open_bridge_folder,
        ).pack(anchor="w", padx=16, pady=(0, 16))

    def build_about(self):
        page = self.pages["О программе"]
        card = self.card(page)
        card.pack(fill="x")
        self.section_title(card, "Telegram PC Bridge", "ⓘ")
        ctk.CTkLabel(
            card,
            text="Версия 4\nЛокальный CustomTkinter-пульт для безопасного управления ПК через Telegram.\n"
                 "Интерфейс выполнен в светлом стиле Windows 11.",
            justify="left", text_color=self.MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=16, pady=(4, 16))

    def show_page(self, name):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        for title, button in self.nav_buttons.items():
            if title == name:
                button.configure(fg_color=self.BLUE_SOFT, text_color="#1769C2")
            else:
                button.configure(fg_color="transparent", text_color=self.TEXT)

    def load_config(self):
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
        except Exception:
            return {}

    def save_config(self):
        CONFIG.write_text(
            json.dumps(
                {
                    "token": self.token.get().strip(),
                    "allowed_user_id": self.allowed_user.get().strip(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def toggle_connection(self):
        if self.client and self.client.running:
            self.stop()
        else:
            self.start()

    def auto_connect(self):
        token = self.token.get().strip()
        uid = self.allowed_user.get().strip()
        if token and (not uid or uid.lstrip("-").isdigit()):
            self.start()

    def start(self):
        token = self.token.get().strip()
        if not token:
            messagebox.showwarning("Token", "Вставьте токен Telegram-бота.")
            return
        uid = self.allowed_user.get().strip()
        if uid and not uid.lstrip("-").isdigit():
            messagebox.showwarning("User ID", "Telegram User ID должен быть числом.")
            return
        if self.client and self.client.running:
            return
        self.save_config()
        self.client = TelegramBotClient(
            token, self.queue_message, self.queue_status, uid or None,
        )
        self.client.start()

    def stop(self):
        if self.client:
            self.client.stop()

    def queue_message(self, message):
        self.events.put(("message", message))

    def queue_status(self, state, text):
        self.events.put(("status", state, text))

    def process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "message":
                    self.add_message(event[1])
                else:
                    self.set_status(event[1], event[2])
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def set_status(self, state, text):
        colors = {
            "online": self.GREEN,
            "connecting": "#F59E0B",
            "error": self.RED,
            "offline": "#94A3B8",
        }
        self.status_dot.configure(text_color=colors.get(state, "#94A3B8"))
        self.status.set(text)

        if state in ("online", "connecting"):
            self.connection_button.configure(
                text="■  Стоп",
                fg_color=self.RED,
                hover_color="#CC363B",
                text_color="#FFFFFF",
            )
        else:
            self.connection_button.configure(
                text="▶  Запустить",
                fg_color=self.BLUE,
                hover_color=self.BLUE_HOVER,
                text_color="#FFFFFF",
            )

    def add_message(self, msg):
        if hasattr(self, "empty_hint") and self.empty_hint.winfo_exists():
            self.empty_hint.place_forget()
        name = msg.get("first_name") or msg.get("username") or str(msg.get("user_id"))
        icons = {
            "voice": "🎤",
            "text": "📱",
            "result": "⚙",
            "security": "🛡",
        }
        text = f"{icons.get(msg['type'], '•')}  {name}  |  {msg['text']}\n"
        if msg.get("file"):
            text += f"Файл: {msg['file']}\n"
        text += f"Chat ID: {msg.get('chat_id')}  •  User ID: {msg.get('user_id')}\n\n"
        self.messages.configure(state="normal")
        self.messages.insert("end", text)
        self.messages.see("end")
        self.messages.configure(state="disabled")
        self.root.bell()

    def clear_messages(self):
        self.messages.configure(state="normal")
        self.messages.delete("1.0", "end")
        self.messages.configure(state="disabled")
        if hasattr(self, "empty_hint"):
            self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")

    def open_downloads(self):
        folder = Path(__file__).with_name("downloads")
        folder.mkdir(exist_ok=True)
        self._open_folder(folder)

    def open_bridge_folder(self):
        self._open_folder(Path(__file__).parent)

    def _open_folder(self, folder):
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            messagebox.showerror("Папка", str(exc))

    def close(self):
        self.stop()
        self.root.destroy()
