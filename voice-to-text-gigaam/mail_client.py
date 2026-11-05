"""Unified mail workspace: IMAP inbox, AI triage/search/reply drafts and confirmed SMTP send."""
from __future__ import annotations
import threading, tkinter as tk
from tkinter import ttk, messagebox, filedialog
from email.utils import parseaddr

def open_mail_client(parent):
    win=tk.Toplevel(parent); win.title("GigaAM — умная почта"); win.geometry("1120x720"); win.minsize(850,560)
    root=ttk.Frame(win,padding=12); root.pack(fill="both",expand=True)
    ttk.Label(root,text="Умная почта",font=("Segoe UI",18,"bold")).pack(anchor="w")
    ttk.Label(root,text="Входящие, поиск, приоритеты и черновики. Письма читаются без изменения статуса; отправка — только после подтверждения.").pack(anchor="w",pady=(2,10))
    toolbar=ttk.Frame(root); toolbar.pack(fill="x")
    query=tk.StringVar(master=win); ttk.Entry(toolbar,textvariable=query).pack(side="left",fill="x",expand=True)
    status=tk.StringVar(master=win,value="Нажми «Загрузить» для чтения почты.")
    body=ttk.Panedwindow(root,orient="horizontal"); body.pack(fill="both",expand=True,pady=10)
    left=ttk.Frame(body); right=ttk.Frame(body); body.add(left,weight=1); body.add(right,weight=2)
    listing=ttk.Treeview(left,columns=("from","subject","date"),show="headings")
    for col,label,width in [("from","От кого",150),("subject","Тема",220),("date","Дата",130)]:
        listing.heading(col,text=label); listing.column(col,width=width,anchor="w")
    listing.pack(fill="both",expand=True)
    details=tk.Text(right,wrap="word",font=("Segoe UI",10)); details.pack(fill="both",expand=True)
    messages=[]; selected={"index":None}
    def show_item(_=None):
        sel=listing.selection()
        if not sel:return
        i=int(sel[0]); selected["index"]=i; item=messages[i]
        details.delete("1.0","end")
        details.insert("1.0",f"От: {item.get('from_name','')} <{item.get('from_email','')}>\nДата: {item.get('date','')}\nТема: {item.get('subject','')}\n\n{item.get('body','')}")
    listing.bind("<<TreeviewSelect>>",show_item)
    def busy(flag,msg):
        status.set(msg)
        for b in buttons.winfo_children(): b.configure(state="disabled" if flag else "normal")
    def load():
        busy(True,"Подключаюсь к IMAP…")
        def work():
            try:
                from mail_reader import fetch_messages
                result=fetch_messages(limit=100, query=query.get().strip())
                err=None
            except Exception as e: result=[]; err=str(e)
            def done():
                messages[:]=result; listing.delete(*listing.get_children()); details.delete("1.0","end")
                if err: status.set("Ошибка: "+err)
                else:
                    for i,m in enumerate(messages): listing.insert("","end",iid=str(i),values=(m.get("from_name") or m.get("from_email"),m.get("subject"),m.get("date")))
                    status.set(f"Загружено писем: {len(messages)}")
                busy(False,status.get())
            win.after(0,done)
        threading.Thread(target=work,daemon=True).start()
    def ai_action(kind):
        if not messages: messagebox.showinfo("Почта","Сначала загрузи письма.",parent=win); return
        if not messagebox.askyesno("Передача текста ИИ","Для анализа выбранные письма будут переданы OpenRouter. Продолжить?",parent=win):return
        busy(True,"ИИ анализирует письма…")
        snapshot=list(messages)
        def work():
            try:
                from ai_chat import ask_ai
                material="\n\n".join(f"От: {m.get('from_email')}\nДата: {m.get('date')}\nТема: {m.get('subject')}\n{m.get('body','')[:5000]}" for m in snapshot)[:28000]
                prompts={
                  "priority":"Разложи письма по важности: срочно, важно, обычно, низкий приоритет. Обоснуй кратко.",
                  "extract":"Выдели по каждому письму просьбы, счета/суммы, сроки, даты и встречи. Если данных нет — так и скажи.",
                  "unanswered":"Найди письма, где от меня ожидают ответ или действие. Не выдумывай, даты писем укажи.",
                  "search":"Найди подходящие письма по запросу пользователя: "+query.get().strip()
                }
                answer=ask_ai(prompts[kind]+"\n\nПисьма:\n"+material,remember=False); err=None
            except Exception as e: answer="";err=str(e)
            def done():
                busy(False,"Анализ завершён." if not err else "Ошибка анализа.")
                details.delete("1.0","end"); details.insert("1.0",answer if not err else err)
            win.after(0,done)
        threading.Thread(target=work,daemon=True).start()
    def compose():
        draft=tk.Toplevel(win); draft.title("Новое письмо"); draft.geometry("680x600")
        f=ttk.Frame(draft,padding=12);f.pack(fill="both",expand=True)
        vars={}
        for label,key in [("Кому","to"),("Тема","subject")]:
            ttk.Label(f,text=label).pack(anchor="w"); vars[key]=tk.StringVar(master=draft)
            ttk.Entry(f,textvariable=vars[key]).pack(fill="x",pady=(2,8))
        ttk.Label(f,text="Текст").pack(anchor="w"); text=tk.Text(f,height=16,wrap="word");text.pack(fill="both",expand=True)
        attach=[]; att=tk.StringVar(master=draft,value="Вложений нет")
        def add():
            attach.extend(p for p in filedialog.askopenfilenames(parent=draft) if p not in attach);att.set("Вложения: "+", ".join(p.split("/")[-1].split("\\\\")[-1] for p in attach))
        ttk.Button(f,text="Добавить вложения",command=add).pack(anchor="w",pady=6);ttk.Label(f,textvariable=att).pack(anchor="w")
        def send():
            to=vars["to"].get().strip(); subject=vars["subject"].get().strip(); content=text.get("1.0","end-1c")
            if not to or not messagebox.askyesno("Подтвердить отправку",f"Отправить письмо?\n\nКому: {to}\nТема: {subject or '(без темы)'}\nВложений: {len(attach)}",parent=draft):return
            button.configure(state="disabled")
            def work():
                try:
                    from email_manager import send_email
                    send_email(to,subject,content,attach); err=None
                except Exception as e:err=str(e)
                def done():
                    if err: messagebox.showerror("Почта",err,parent=draft);button.configure(state="normal")
                    else: messagebox.showinfo("Почта","Письмо отправлено.",parent=draft);draft.destroy()
                draft.after(0,done)
            threading.Thread(target=work,daemon=True).start()
        button=ttk.Button(f,text="Отправить…",command=send);button.pack(anchor="e",pady=8)
    buttons=ttk.Frame(root);buttons.pack(fill="x")
    for label,cmd in [("Загрузить / обновить",load),("Важность",lambda:ai_action("priority")),("Просьбы, счета и сроки",lambda:ai_action("extract")),("Давно ждут ответа",lambda:ai_action("unanswered")),("Найти письма",lambda:ai_action("search")),("Новое письмо",compose)]:
        ttk.Button(buttons,text=label,command=cmd).pack(side="left",padx=(0,5))
    ttk.Label(root,textvariable=status).pack(anchor="w",pady=(8,0))
    load()
