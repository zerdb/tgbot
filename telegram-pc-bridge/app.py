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
        self.root.title("Telegram PC Bridge • Remote Control")
        self.root.geometry("960x690")
        self.root.minsize(780, 560)
        self.client = None
        self.events = queue.Queue()
        config = self.load_config()
        self.token = tk.StringVar(value=config.get("token", ""))
        self.allowed_user = tk.StringVar(value=str(config.get("allowed_user_id", "")))
        self.status = tk.StringVar(value="Остановлен")
        self.build_ui()
        self.root.after(100, self.process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self):
        style = ttk.Style()
        if "clam" in style.theme_names(): style.theme_use("clam")
        style.configure("TButton", padding=(12, 8))
        style.configure("Accent.TButton", padding=(14, 9), font=("TkDefaultFont", 10, "bold"))
        main = ttk.Frame(self.root, padding=18); main.pack(fill="both", expand=True)
        ttk.Label(main, text="Telegram → PC Remote Control", font=("TkDefaultFont", 20, "bold")).pack(anchor="w")
        ttk.Label(main, text="Безопасный allow-list: Telegram-команды управляют только заранее разрешёнными действиями.").pack(anchor="w", pady=(3, 16))

        connection = ttk.LabelFrame(main, text=" Подключение ", padding=10); connection.pack(fill="x")
        ttk.Label(connection, text="Bot Token:").grid(row=0,column=0,sticky="w")
        ttk.Entry(connection,textvariable=self.token,show="•").grid(row=0,column=1,sticky="ew",padx=8)
        ttk.Label(connection,text="Ваш Telegram User ID:").grid(row=1,column=0,sticky="w",pady=(8,0))
        ttk.Entry(connection,textvariable=self.allowed_user).grid(row=1,column=1,sticky="ew",padx=8,pady=(8,0))
        connection.columnconfigure(1,weight=1)
        ttk.Button(connection,text="▶ Запустить",style="Accent.TButton",command=self.start).grid(row=0,column=2,rowspan=2,padx=(4,0))
        ttk.Button(connection,text="■ Стоп",command=self.stop).grid(row=0,column=3,rowspan=2,padx=(7,0))

        status_row=ttk.Frame(main); status_row.pack(fill="x",pady=10)
        self.status_dot=tk.Label(status_row,text="●",fg="#888888"); self.status_dot.pack(side="left")
        ttk.Label(status_row,textvariable=self.status).pack(side="left",padx=5)
        ttk.Button(status_row,text="📂 Голосовые",command=self.open_downloads).pack(side="right")
        ttk.Button(status_row,text="🧹 Очистить",command=self.clear_messages).pack(side="right",padx=7)

        info=ttk.LabelFrame(main,text=" Команды с телефона ",padding=8); info.pack(fill="x",pady=(0,10))
        ttk.Label(info,text="В Telegram появится панель: 🖥 Статус • 📝 Блокнот • 🧮 Калькулятор • 📁 Проводник • 📂 Файлы").pack(anchor="w")

        box=ttk.LabelFrame(main,text=" Журнал ",padding=8); box.pack(fill="both",expand=True)
        self.messages=tk.Text(box,wrap="word",state="disabled",font=("TkDefaultFont",10),padx=10,pady=10)
        scroll=ttk.Scrollbar(box,command=self.messages.yview); self.messages.configure(yscrollcommand=scroll.set)
        self.messages.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y")
        ttk.Label(main,text="Важно: задайте свой User ID — тогда команды других пользователей будут заблокированы.").pack(anchor="w",pady=(9,0))

    def load_config(self):
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
        except Exception: return {}

    def save_config(self):
        CONFIG.write_text(json.dumps({"token":self.token.get().strip(),"allowed_user_id":self.allowed_user.get().strip()},indent=2),encoding="utf-8")

    def start(self):
        token=self.token.get().strip()
        if not token:
            messagebox.showwarning("Token","Вставьте токен Telegram-бота."); return
        uid=self.allowed_user.get().strip()
        if uid and not uid.lstrip("-").isdigit():
            messagebox.showwarning("User ID","Telegram User ID должен быть числом."); return
        if self.client and self.client.running: return
        self.save_config()
        self.client=TelegramBotClient(token,self.queue_message,self.queue_status,uid or None)
        self.client.start()

    def stop(self):
        if self.client: self.client.stop()
    def queue_message(self,message): self.events.put(("message",message))
    def queue_status(self,state,text): self.events.put(("status",state,text))

    def process_events(self):
        try:
            while True:
                event=self.events.get_nowait()
                self.add_message(event[1]) if event[0]=="message" else self.set_status(event[1],event[2])
        except queue.Empty: pass
        self.root.after(100,self.process_events)

    def set_status(self,state,text):
        colors={"online":"#28a745","connecting":"#e0a800","error":"#dc3545","offline":"#888888"}
        self.status_dot.configure(fg=colors.get(state,"#888888")); self.status.set(text)

    def add_message(self,msg):
        name=msg.get("first_name") or msg.get("username") or str(msg.get("user_id"))
        icons={"voice":"🎤","text":"📱","result":"⚙","security":"🛡"}
        text=f"{icons.get(msg['type'],'•')} {name} | {msg['text']}\n"
        if msg.get("file"): text+=f"Файл: {msg['file']}\n"
        text+=f"Chat ID: {msg.get('chat_id')}  User ID: {msg.get('user_id')}\n\n"
        self.messages.configure(state="normal"); self.messages.insert("end",text); self.messages.see("end"); self.messages.configure(state="disabled")
        self.root.bell()

    def clear_messages(self):
        self.messages.configure(state="normal"); self.messages.delete("1.0","end"); self.messages.configure(state="disabled")

    def open_downloads(self):
        folder=Path(__file__).with_name("downloads"); folder.mkdir(exist_ok=True)
        try:
            if sys.platform.startswith("win"): os.startfile(folder)
            elif sys.platform=="darwin": subprocess.Popen(["open",folder])
            else: subprocess.Popen(["xdg-open",folder])
        except Exception as exc: messagebox.showerror("Папка",str(exc))

    def close(self):
        self.stop(); self.root.destroy()
