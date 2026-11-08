"""Mail client with rich HTML message rendering and confirmed sending."""
from __future__ import annotations
import html
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from dialog_utils import center_window, apply_modern_style


def open_mail_client(parent):
    win=tk.Toplevel(parent); win.title("Zero Control — почта"); win.geometry("1160x760"); win.minsize(900,600)
    apply_modern_style(win)
    root=ttk.Frame(win,padding=12); root.pack(fill="both",expand=True)
    ttk.Label(root,text="✉  Почта",font=("Segoe UI",18,"bold")).pack(anchor="w")
    ttk.Label(root,text="Письма отображаются в HTML, если отправитель прислал HTML-версию.").pack(anchor="w",pady=(2,10))
    toolbar=ttk.Frame(root); toolbar.pack(fill="x")
    query=tk.StringVar(master=win)
    search_entry=ttk.Entry(toolbar,textvariable=query)
    search_entry.pack(side="left",fill="x",expand=True,padx=(0,8))
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
    loading_overlay=None
    loading_label=None
    def show_loading(message):
        nonlocal loading_overlay, loading_label
        if loading_overlay is None or not loading_overlay.winfo_exists():
            loading_overlay=tk.Toplevel(win)
            loading_overlay.overrideredirect(True)
            loading_overlay.attributes("-topmost",True)
            loading_overlay.attributes("-alpha",0.96)
            loading_overlay.configure(bg="#202124")
            frame=tk.Frame(loading_overlay,bg="#202124",padx=16,pady=10)
            frame.pack()
            tk.Label(frame,text="⏳",font=("Segoe UI Emoji",22),fg="#fbbc04",bg="#202124").pack(side="left",padx=(0,9))
            loading_label=tk.Label(frame,text="",font=("Segoe UI",10,"bold"),fg="white",bg="#202124")
            loading_label.pack(side="left")
        loading_label.configure(text=message)
        loading_overlay.update_idletasks()
        w,h=loading_overlay.winfo_reqwidth(),loading_overlay.winfo_reqheight()
        x=win.winfo_screenwidth()-w-24
        y=(win.winfo_screenheight()-h)//2
        loading_overlay.geometry(f"+{x}+{y}")
        loading_overlay.deiconify()
        loading_overlay.lift()

    def hide_loading():
        nonlocal loading_overlay, loading_label
        if loading_overlay is not None:
            try: loading_overlay.destroy()
            except tk.TclError: pass
        loading_overlay=None
        loading_label=None

    def load():
        status.set("Подключаюсь к почте…")
        load_button.configure(state="disabled")
        show_loading("Загружаю почту…")
        win.update_idletasks()
        search_text=query.get().strip()
        def work():
            try:
                from mail_reader import fetch_messages
                result=fetch_messages(limit=100,query=search_text); err=None
            except Exception as exc: result=[]; err=str(exc)
            def done():
                if not win.winfo_exists(): return
                messages[:]=result; listing.delete(*listing.get_children())
                if html_supported: viewer.load_html("<html><body style='font-family:Segoe UI;padding:24px'>Выбери письмо слева.</body></html>")
                else: plain.delete("1.0","end")
                if err: status.set("Ошибка загрузки: "+err)
                else:
                    for i,m in enumerate(messages):
                        listing.insert("","end",iid=str(i),values=(m.get("from_name") or m.get("from_email"),m.get("subject"),m.get("date")))
                    status.set(f"Загружено писем: {len(messages)}")
                    if messages:
                        first=listing.get_children()[0]; listing.selection_set(first); listing.focus(first); show_item()
                load_button.configure(state="normal")
                hide_loading()
            try: win.after(0,done)
            except tk.TclError: pass
        threading.Thread(target=work,daemon=True,name="mail-load").start()
    buttons=ttk.Frame(root); buttons.pack(fill="x")
    load_button=ttk.Button(buttons,text="↻  Обновить",command=load); load_button.pack(side="left",padx=(0,6))
    search_entry.bind("<Return>",lambda _event: load())
    ttk.Label(root,textvariable=status).pack(anchor="w",pady=(8,0))
    center_window(win,parent)
    load()
