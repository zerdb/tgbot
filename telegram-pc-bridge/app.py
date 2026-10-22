import json
import os
import queue
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from telegram_client import TelegramBotClient

CONFIG = Path(__file__).with_name("config.json")

class TelegramBridgeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram PC Bridge")
        self.root.geometry("920x650")
        self.root.minsize(760, 520)
        self.client = None
        self.events = queue.Queue()
        self.token = tk.StringVar(value=self.load_token())
        self.status = tk.StringVar(value="Остановлен")
        self.build_ui()
        self.root.after(100, self.process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TButton", padding=(12, 8))
        style.configure("Accent.TButton", padding=(14, 9), font=("TkDefaultFont", 10, "bold"))

        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Telegram → PC Bridge", font=("TkDefaultFont", 20, "bold")).pack(anchor="w")
        ttk.Label(main, text="Локальная панель: сообщения боту с телефона появляются на этом компьютере.").pack(anchor="w", pady=(3, 16))

        connection = ttk.LabelFrame(main, text=" Подключение ", padding=10)
        connection.pack(fill="x")
        ttk.Label(connection, text="Bot Token:").pack(side="left")
        ttk.Entry(connection, textvariable=self.token, show="•").pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(connection, text="▶ Запустить", style="Accent.TButton", command=self.start).pack(side="left")
        ttk.Button(connection, text="■ Стоп", command=self.stop).pack(side="left", padx=(7, 0))

        status_row = ttk.Frame(main)
        status_row.pack(fill="x", pady=10)
        self.status_dot = tk.Label(status_row, text="●", fg="#888888")
        self.status_dot.pack(side="left")
        ttk.Label(status_row, textvariable=self.status).pack(side="left", padx=5)
        ttk.Button(status_row, text="📂 Голосовые", command=self.open_downloads).pack(side="right")
        ttk.Button(status_row, text="🧹 Очистить", command=self.clear_messages).pack(side="right", padx=7)

        box = ttk.LabelFrame(main, text=" Входящие сообщения ", padding=8)
        box.pack(fill="both", expand=True)

        self.messages = tk.Text(box, wrap="word", state="disabled", font=("TkDefaultFont", 10), padx=10, pady=10)
        scroll = ttk.Scrollbar(box, command=self.messages.yview)
        self.messages.configure(yscrollcommand=scroll.set)
        self.messages.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Label(main, text="Текст показывается сразу. Голосовые скачиваются в папку downloads в формате OGG.").pack(anchor="w", pady=(9, 0))

    def load_token(self):
        try:
            if CONFIG.exists():
                return json.loads(CONFIG.read_text(encoding="utf-8")).get("token", "")
        except Exception:
            pass
        return ""

    def save_token(self):
        CONFIG.write_text(json.dumps({"token": self.token.get().strip()}, indent=2), encoding="utf-8")

    def start(self):
        token = self.token.get().strip()
        if not token:
            messagebox.showwarning("Token", "Вставьте токен Telegram-бота.")
            return
        if self.client and self.client.running:
            return
        try:
            self.save_token()
        except OSError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return
        self.client = TelegramBotClient(token, self.queue_message, self.queue_status)
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
        colors = {"online": "#28a745", "connecting": "#e0a800", "error": "#dc3545", "offline": "#888888"}
        self.status_dot.configure(fg=colors.get(state, "#888888"))
        self.status.set(text)

    def add_message(self, msg):
        name = msg.get("first_name") or msg.get("username") or str(msg.get("user_id"))
        username = f" @{msg['username']}" if msg.get("username") else ""
        icon = "🎤" if msg["type"] == "voice" else "💬" if msg["type"] == "text" else "•"
        text = f"{icon} {name}{username}\n{msg['text']}\n"
        if msg.get("file"):
            text += f"Файл: {msg['file']}\n"
        text += f"Chat ID: {msg.get('chat_id')}  User ID: {msg.get('user_id')}\n\n"
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
