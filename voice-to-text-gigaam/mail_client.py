"""Mail client with rich HTML message rendering and confirmed sending."""
from __future__ import annotations
import html
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dialog_utils import center_window


def open_mail_client(parent):
    win=tk.Toplevel(parent); win.title("GigaAM — почта"); win.geometry("1160x760"); win.minsize(900,600)
    root=ttk.Frame(win,padding=12); root.pack(fill="both",expand=True)
    ttk.Label(root,text="✉  Почта",font=("Segoe UI",18,"bold")).pack(anchor="w")
    ttk.Label(root,text="Письма отображаются в HTML, если отправитель прислал HTML-версию.").pack(anchor="w",pady=(2,10))
    toolbar=ttk.Frame(root); toolbar.pack(fill="x")
    query=tk.StringVar(master=win)
    ttk.Entry(toolbar,textvariable=query).pack(side="left",fill="x",expand=True,padx=(0,8))
    status=tk.StringVar(master=win,value="Загружаю входящие…")
    body=ttk.Panedwindow(root,orient="horizontal"); body.pack(fill="both",expand=True,pady=10)
    left=ttk.Frame(body); right=ttk.Frame(body); body.add(left,weight=1); body.add(right,weight=2)
    listing=ttk.Treeview(left,columns=("from","subject","date"),show="headings")
    for col,label,width in [("from","От кого",150),("subject","Тема",230),("date","Дата",130)]:
        listing.heading(col,text=label); listing.column(col,width=width,anchor="w")
    listing.pack(fill="both",expand=True)
    viewer=None
    try:
        from tkinterweb import HtmlFrame
        viewer=HtmlFrame(right, messages_enabled=False)
        viewer.pack(fill="both",expand=True)
        html_supported=True
    except Exception:
        html_supported=False
        plain=tk.Text(right,wrap="word",font=("Segoe UI",10)); plain.pack(fill="both",expand=True)
    messages=[]
    def display(item):
        if html_supported:
            source=item.get("html_body") or ("<!doctype html><html><body style='font-family:Segoe UI,Arial;padding:18px;white-space:pre-wrap'>"+html.escape(item.get("body",""))+"</body></html>")
            viewer.load_html(source)
        else:
            plain.delete("1.0","end")
            plain.insert("1.0","HTML-просмотрщик не установлен. Текстовая версия письма:\n\n"+item.get("body",""))
    def show_item(_=None):
        sel=listing.selection()
        if not sel:return
        i=int(sel[0]); item=messages[i]
        header=f"<div style='font:14px Segoe UI;padding:10px;background:#f1f3f4'><b>{html.escape(item.get('subject') or '(без темы)')}</b><br>От: {html.escape(item.get('from_name') or '')} &lt;{html.escape(item.get('from_email') or '')}&gt;<br>{html.escape(item.get('date') or '')}</div>"
        if html_supported:
            source=item.get("html_body") or ("<html><body style='font-family:Segoe UI,Arial;padding:18px;white-space:pre-wrap'>"+html.escape(item.get("body",""))+"</body></html>")
            viewer.load_html(header+source.replace("<body","<body style='font-family:Segoe UI,Arial;padding:18px'"))
        else: display(item)
    listing.bind("<<TreeviewSelect>>",show_item)
    def load():
        status.set("↻  Подключаюсь к почте…")
        for b in buttons.winfo_children(): b.configure(state="disabled")
        def work():
            try:
                from mail_reader import fetch_messages
                result=fetch_messages(limit=100,query=query.get().strip()); err=None
            except Exception as exc: result=[]; err=str(exc)
            def done():
                messages[:]=result; listing.delete(*listing.get_children())
                if html_supported: viewer.load_html("<html><body style='font-family:Segoe UI;padding:24px'>Выбери письмо слева.</body></html>")
                else: plain.delete("1.0","end")
                if err: status.set("Ошибка загрузки: "+err)
                else:
                    for i,m in enumerate(messages):
                        listing.insert("","end",iid=str(i),values=(m.get("from_name") or m.get("from_email"),m.get("subject"),m.get("date")))
                    status.set(f"✓  Загружено писем: {len(messages)}")
                    if messages:
                        first=listing.get_children()[0]; listing.selection_set(first); listing.focus(first); show_item()
                for b in buttons.winfo_children(): b.configure(state="normal")
            win.after(0,done)
        threading.Thread(target=work,daemon=True,name="mail-load").start()
    def compose():
        draft=tk.Toplevel(win); draft.title("Новое письмо"); draft.geometry("700x620")
        frame=ttk.Frame(draft,padding=14); frame.pack(fill="both",expand=True)
        fields={}
        for label,key in [("Кому","to"),("Тема","subject")]:
            ttk.Label(frame,text=label).pack(anchor="w")
            fields[key]=tk.StringVar(master=draft)
            ttk.Entry(frame,textvariable=fields[key]).pack(fill="x",pady=(2,8))
        ttk.Label(frame,text="Текст письма").pack(anchor="w")
        editor=tk.Text(frame,height=17,wrap="word"); editor.pack(fill="both",expand=True)
        attachments=[]; attachment_label=tk.StringVar(master=draft,value="Вложений нет")
        def add_files():
            for item in filedialog.askopenfilenames(parent=draft):
                if item not in attachments: attachments.append(item)
            attachment_label.set("Вложения: "+", ".join(p.replace("\\","/").split("/")[-1] for p in attachments) if attachments else "Вложений нет")
        ttk.Button(frame,text="📎  Добавить вложения",command=add_files).pack(anchor="w",pady=6)
        ttk.Label(frame,textvariable=attachment_label).pack(anchor="w")
        def send():
            recipient=fields["to"].get().strip()
            if not recipient:
                messagebox.showwarning("Почта","Укажи получателя.",parent=draft); return
            subject=fields["subject"].get().strip(); text=editor.get("1.0","end-1c")
            if not messagebox.askyesno("Подтвердить отправку",f"Отправить письмо?\n\nКому: {recipient}\nТема: {subject or '(без темы)'}\nВложений: {len(attachments)}",parent=draft): return
            send_button.configure(state="disabled")
            def worker():
                try:
                    from email_manager import send_email
                    send_email(recipient,subject,text,attachments); error=None
                except Exception as exc: error=str(exc)
                def finish():
                    if error:
                        messagebox.showerror("Почта",error,parent=draft); send_button.configure(state="normal")
                    else:
                        messagebox.showinfo("Почта","Письмо отправлено.",parent=draft); draft.destroy()
                draft.after(0,finish)
            threading.Thread(target=worker,daemon=True).start()
        send_button=ttk.Button(frame,text="➤  Отправить",command=send); send_button.pack(anchor="e",pady=8)
        center_window(draft,win)
    buttons=ttk.Frame(root); buttons.pack(fill="x")
    ttk.Button(buttons,text="↻  Обновить",command=load).pack(side="left",padx=(0,6))
    ttk.Button(buttons,text="✉  Новое письмо",command=compose).pack(side="left")
    ttk.Label(root,textvariable=status).pack(anchor="w",pady=(8,0))
    center_window(win,parent)
    load()
