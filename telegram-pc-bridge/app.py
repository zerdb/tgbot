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
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram PC Bridge  •  Windows 11")
        self.root.geometry("1120x760")
        self.root.minsize(900, 620)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.client = None
        self.events = queue.Queue()
        config = self.load_config()
        self.token = ctk.StringVar(value=config.get("token", ""))
        self.allowed_user = ctk.StringVar(value=str(config.get("allowed_user_id", "")))
        self.status = ctk.StringVar(value="Остановлен")
        self.build_ui()
        self.root.after(100, self.process_events)
        self.root.after(350, self.auto_connect)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self):
        self.root.configure(bg="#F3F6FB")
        shell = ctk.CTkFrame(self.root, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=28, pady=24)

        header = ctk.CTkFrame(shell, fg_color="transparent")
        header.pack(fill="x", pady=(0, 18))
        ctk.CTkLabel(
            header,
            text="Telegram PC Bridge",
            text_color="#172033",
            font=ctk.CTkFont(size=30, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Удалённое управление ПК через Telegram  •  Windows 11 UI",
            text_color="#64748B",
            font=ctk.CTkFont(size=14),
        ).pack(anchor="w", pady=(3, 0))

        connection = ctk.CTkFrame(
            shell,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#E2E8F0",
            corner_radius=16,
        )
        connection.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            connection,
            text="ПОДКЛЮЧЕНИЕ",
            text_color="#64748B",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(
            connection,
            text="Bot Token",
            text_color="#334155",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=1, column=0, sticky="w", padx=(18, 8), pady=7)
        ctk.CTkEntry(
            connection,
            textvariable=self.token,
            show="•",
            height=40,
            corner_radius=10,
            fg_color="#F8FAFC",
            border_color="#CBD5E1",
            text_color="#0F172A",
        ).grid(row=1, column=1, sticky="ew", padx=8, pady=7)
        ctk.CTkLabel(
            connection,
            text="Telegram User ID",
            text_color="#334155",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=2, column=0, sticky="w", padx=(18, 8), pady=7)
        ctk.CTkEntry(
            connection,
            textvariable=self.allowed_user,
            height=40,
            corner_radius=10,
            fg_color="#F8FAFC",
            border_color="#CBD5E1",
            text_color="#0F172A",
        ).grid(row=2, column=1, sticky="ew", padx=8, pady=7)

        buttons = ctk.CTkFrame(connection, fg_color="transparent")
        buttons.grid(row=1, column=2, rowspan=2, padx=(8, 18), pady=7)
        ctk.CTkButton(
            buttons,
            text="▶  Запустить",
            width=130,
            height=40,
            corner_radius=10,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self.start,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            buttons,
            text="■  Стоп",
            width=100,
            height=40,
            corner_radius=10,
            fg_color="#E2E8F0",
            hover_color="#CBD5E1",
            text_color="#334155",
            command=self.stop,
        ).pack(side="left", padx=4)
        connection.columnconfigure(1, weight=1)

        cards = ctk.CTkFrame(shell, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 14))

        self.status_card = ctk.CTkFrame(
            cards,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#E2E8F0",
            corner_radius=16,
        )
        self.status_card.pack(side="left", fill="x", expand=True, padx=(0, 7))
        self.status_dot = ctk.CTkLabel(
            self.status_card,
            text="●",
            font=ctk.CTkFont(size=20),
            text_color="#94A3B8",
        )
        self.status_dot.pack(side="left", padx=(18, 8), pady=16)
        ctk.CTkLabel(
            self.status_card,
            textvariable=self.status,
            text_color="#172033",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            self.status_card,
            text="📂  Открыть файлы",
            width=150,
            height=34,
            corner_radius=9,
            fg_color="#F1F5F9",
            hover_color="#E2E8F0",
            text_color="#334155",
            command=self.open_downloads,
        ).pack(side="right", padx=14)

        info = ctk.CTkFrame(
            cards,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#E2E8F0",
            corner_radius=16,
        )
        info.pack(side="left", fill="x", expand=True, padx=(7, 0))
        ctk.CTkLabel(
            info,
            text="🛡  Защищённый режим",
            text_color="#172033",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(
            info,
            text="Allow-list команд • User ID • подтверждения опасных действий",
            text_color="#64748B",
        ).pack(anchor="w", padx=18, pady=(0, 14))

        journal = ctk.CTkFrame(
            shell,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#E2E8F0",
            corner_radius=16,
        )
        journal.pack(fill="both", expand=True)
        top = ctk.CTkFrame(journal, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 7))
        ctk.CTkLabel(
            top,
            text="Журнал активности",
            text_color="#172033",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            top,
            text="🧹 Очистить",
            width=100,
            height=32,
            corner_radius=8,
            fg_color="#F1F5F9",
            hover_color="#E2E8F0",
            text_color="#334155",
            command=self.clear_messages,
        ).pack(side="right")
        self.messages = ctk.CTkTextbox(
            journal,
            corner_radius=10,
            border_width=0,
            fg_color="#F8FAFC",
            text_color="#334155",
            font=ctk.CTkFont(size=13),
        )
        self.messages.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.messages.configure(state="disabled")

        ctk.CTkLabel(
            shell,
            text="Конфигурация хранится локально и не отправляется в Git.",
            text_color="#64748B",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(8, 0))

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

    def auto_connect(self):
        """Подключается автоматически, если локальная конфигурация уже заполнена."""
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
            token,
            self.queue_message,
            self.queue_status,
            uid or None,
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
            "online": "#22C55E",
            "connecting": "#F59E0B",
            "error": "#EF4444",
            "offline": "#94A3B8",
        }
        self.status_dot.configure(text_color=colors.get(state, "#94A3B8"))
        self.status.set(text)

    def add_message(self, msg):
        name = msg.get("first_name") or msg.get("username") or str(msg.get("user_id"))
        icons = {
            "voice": "🎤",
            "text": "📱",
            "result": "⚙️",
            "security": "🛡️",
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

    def open_downloads(self):
        folder = Path(__file__).with_name("downloads")
        folder.mkdir(exist_ok=True)
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
