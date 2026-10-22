import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
from database import Database

BG="#111827"; PANEL="#182235"; CARD="#202c42"; TEXT="#eef2ff"; MUTED="#9aa8bf"; ACCENT="#5b8cff"; GREEN="#44c98a"; RED="#ff667a"

class LifeManagerApp:
    def __init__(self, root):
        self.root=root
        self.db=Database()
        self.root.title("Life Manager")
        self.root.geometry("1120x700")
        self.root.minsize(900,600)
        self.root.configure(bg=BG)
        self.current_note=None
        self.setup_style()
        self.build()

    def setup_style(self):
        s=ttk.Style()
        if "clam" in s.theme_names(): s.theme_use("clam")
        s.configure("TFrame",background=BG)
        s.configure("Panel.TFrame",background=PANEL)
        s.configure("TLabel",background=BG,foreground=TEXT,font=("Segoe UI",10))
        s.configure("Title.TLabel",background=BG,foreground=TEXT,font=("Segoe UI",24,"bold"))
        s.configure("Muted.TLabel",background=BG,foreground=MUTED)
        s.configure("TButton",font=("Segoe UI",10),padding=(12,8))
        s.configure("Accent.TButton",font=("Segoe UI",10,"bold"),padding=(14,9))
        s.configure("Treeview",background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=31,borderwidth=0)
        s.configure("Treeview.Heading",font=("Segoe UI",10,"bold"),padding=8)
        s.map("Treeview",background=[("selected",ACCENT)])

    def build(self):
        shell=ttk.Frame(self.root); shell.pack(fill="both",expand=True)
        nav=tk.Frame(shell,bg=PANEL,width=210); nav.pack(side="left",fill="y"); nav.pack_propagate(False)
        tk.Label(nav,text="◈ LIFE MANAGER",bg=PANEL,fg=TEXT,font=("Segoe UI",16,"bold"),pady=24).pack(fill="x")
        for text,cmd in [("⌂  Обзор",self.show_dashboard),("✓  Задачи",self.show_tasks),("★  Привычки",self.show_habits),("▤  Заметки",self.show_notes)]:
            tk.Button(nav,text=text,command=cmd,anchor="w",bg=PANEL,fg=TEXT,activebackground=CARD,activeforeground=TEXT,relief="flat",bd=0,font=("Segoe UI",11),padx=22,pady=13,cursor="hand2").pack(fill="x")
        tk.Label(nav,text="Python • Tkinter • SQLite",bg=PANEL,fg=MUTED,font=("Segoe UI",8)).pack(side="bottom",pady=16)
        self.content=ttk.Frame(shell,padding=26); self.content.pack(side="left",fill="both",expand=True)
        self.show_dashboard()

    def clear(self):
        for w in self.content.winfo_children(): w.destroy()

    def heading(self,title,subtitle=""):
        ttk.Label(self.content,text=title,style="Title.TLabel").pack(anchor="w")
        if subtitle: ttk.Label(self.content,text=subtitle,style="Muted.TLabel").pack(anchor="w",pady=(2,18))

    def show_dashboard(self):
        self.clear(); self.heading("Обзор","Сегодня • "+date.today().strftime("%d.%m.%Y"))
        tasks,habits,today,notes=self.db.stats()
        cards=ttk.Frame(self.content); cards.pack(fill="x")
        data=[("Задачи",f"{tasks['done']} / {tasks['total']}","выполнено"),("Привычки",f"{today} / {habits}","сегодня"),("Заметки",str(notes),"сохранено")]
        for title,value,sub in data:
            box=tk.Frame(cards,bg=CARD,padx=20,pady=18); box.pack(side="left",fill="x",expand=True,padx=(0,12))
            tk.Label(box,text=title,bg=CARD,fg=MUTED,font=("Segoe UI",10)).pack(anchor="w")
            tk.Label(box,text=value,bg=CARD,fg=TEXT,font=("Segoe UI",26,"bold")).pack(anchor="w",pady=5)
            tk.Label(box,text=sub,bg=CARD,fg=MUTED,font=("Segoe UI",9)).pack(anchor="w")
        tk.Label(self.content,text="Добро пожаловать. Здесь собраны задачи, привычки и заметки в одном локальном приложении.",bg=BG,fg=MUTED,font=("Segoe UI",11),pady=35).pack(anchor="w")

    def show_tasks(self):
        self.clear(); self.heading("Задачи","Планируйте дела и отмечайте выполненное")
        form=ttk.Frame(self.content); form.pack(fill="x",pady=(0,14))
        title=ttk.Entry(form); title.pack(side="left",fill="x",expand=True,ipady=5)
        category=ttk.Combobox(form,values=["Общее","Работа","Учёба","Дом","Личное"],width=13); category.set("Общее"); category.pack(side="left",padx=7)
        priority=ttk.Combobox(form,values=["Низкий","Средний","Высокий"],width=10); priority.set("Средний"); priority.pack(side="left")
        due=ttk.Entry(form,width=13); due.insert(0,"дд.мм.гггг"); due.pack(side="left",padx=7)
        def add():
            if title.get().strip():
                self.db.add_task(title.get().strip(),category.get(),priority.get(),due.get().strip()); self.show_tasks()
        ttk.Button(form,text="+ Добавить",style="Accent.TButton",command=add).pack(side="left")
        tree=ttk.Treeview(self.content,columns=("state","title","cat","priority","due"),show="headings")
        for col,text,w in [("state","",55),("title","Задача",360),("cat","Категория",120),("priority","Приоритет",110),("due","Срок",110)]:
            tree.heading(col,text=text); tree.column(col,width=w,anchor="w")
        tree.pack(fill="both",expand=True)
        for r in self.db.tasks(): tree.insert("", "end", iid=r["id"], values=("✓" if r["done"] else "○",r["title"],r["category"],r["priority"],r["due_date"]))
        actions=ttk.Frame(self.content); actions.pack(fill="x",pady=10)
        def selected():
            s=tree.selection(); return int(s[0]) if s else None
        ttk.Button(actions,text="✓ Выполнено / вернуть",command=lambda: (self.db.toggle_task(selected()),self.show_tasks()) if selected() else None).pack(side="left")
        ttk.Button(actions,text="🗑 Удалить",command=lambda: (self.db.delete_task(selected()),self.show_tasks()) if selected() else None).pack(side="left",padx=7)
        tree.bind("<Double-1>",lambda e: (self.db.toggle_task(selected()),self.show_tasks()) if selected() else None)

    def show_habits(self):
        self.clear(); self.heading("Привычки","Отмечайте ежедневный прогресс")
        form=ttk.Frame(self.content); form.pack(fill="x",pady=(0,16))
        name=ttk.Entry(form); name.pack(side="left",fill="x",expand=True,ipady=5)
        def add():
            if name.get().strip(): self.db.add_habit(name.get().strip()); self.show_habits()
        ttk.Button(form,text="+ Новая привычка",style="Accent.TButton",command=add).pack(side="left",padx=(8,0))
        for h in self.db.habits():
            row=tk.Frame(self.content,bg=CARD,padx=16,pady=12); row.pack(fill="x",pady=5)
            tk.Label(row,text="✓" if h["done_today"] else "○",bg=CARD,fg=GREEN if h["done_today"] else MUTED,font=("Segoe UI",18,"bold")).pack(side="left")
            tk.Label(row,text=h["name"],bg=CARD,fg=TEXT,font=("Segoe UI",11,"bold"),padx=12).pack(side="left")
            tk.Label(row,text=f"Всего отметок: {h['total']}",bg=CARD,fg=MUTED).pack(side="left")
            tk.Button(row,text="Удалить",command=lambda i=h["id"]: (self.db.delete_habit(i),self.show_habits()),bg=CARD,fg=RED,relief="flat").pack(side="right")
            tk.Button(row,text="Отметить сегодня",command=lambda i=h["id"]: (self.db.toggle_habit(i),self.show_habits()),bg=ACCENT,fg="white",relief="flat",padx=12,pady=5).pack(side="right",padx=8)

    def show_notes(self):
        self.clear(); self.heading("Заметки","Локальный блокнот с автосохранением по кнопке")
        area=ttk.Frame(self.content); area.pack(fill="both",expand=True)
        left=tk.Frame(area,bg=PANEL,width=260); left.pack(side="left",fill="y"); left.pack_propagate(False)
        right=ttk.Frame(area,padding=(16,0,0,0)); right.pack(side="left",fill="both",expand=True)
        lst=tk.Listbox(left,bg=PANEL,fg=TEXT,selectbackground=ACCENT,relief="flat",bd=0,font=("Segoe UI",10)); lst.pack(fill="both",expand=True,padx=8,pady=8)
        rows=self.db.notes()
        for n in rows: lst.insert("end",n["title"])
        title=ttk.Entry(right,font=("Segoe UI",12)); title.pack(fill="x",ipady=5)
        body=tk.Text(right,bg=CARD,fg=TEXT,insertbackground=TEXT,relief="flat",font=("Segoe UI",11),wrap="word",padx=12,pady=12); body.pack(fill="both",expand=True,pady=10)
        self.current_note=None
        def load(_=None):
            sel=lst.curselection()
            if not sel: return
            n=rows[sel[0]]; self.current_note=n["id"]
            title.delete(0,"end"); title.insert(0,n["title"])
            body.delete("1.0","end"); body.insert("1.0",n["body"])
        lst.bind("<<ListboxSelect>>",load)
        def new():
            self.current_note=None; title.delete(0,"end"); body.delete("1.0","end"); title.focus()
        def save():
            if title.get().strip():
                self.db.save_note(self.current_note,title.get().strip(),body.get("1.0","end-1c")); self.show_notes()
        def delete():
            if self.current_note and messagebox.askyesno("Удалить","Удалить эту заметку?"):
                self.db.delete_note(self.current_note); self.show_notes()
        bar=ttk.Frame(right); bar.pack(fill="x")
        ttk.Button(bar,text="+ Новая",command=new).pack(side="left")
        ttk.Button(bar,text="💾 Сохранить",style="Accent.TButton",command=save).pack(side="left",padx=7)
        ttk.Button(bar,text="🗑 Удалить",command=delete).pack(side="left")
