"""Reminder manager window."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk,messagebox
from dialog_utils import center_window, apply_modern_style
def open_reminders(parent):
    from reminders import list_reminders, delete_reminder, add_reminder
    win=tk.Toplevel(parent);win.title("GigaAM — напоминания");win.geometry("760x520");win.minsize(560,380)
    apply_modern_style(win)
    center_window(win,parent)
    f=ttk.Frame(win,padding=14);f.pack(fill="both",expand=True)
    ttk.Label(f,text="Напоминания",font=("Segoe UI",17,"bold")).pack(anchor="w")
    ttk.Label(f,text="Все запланированные события. Срабатывание сопровождается уведомлением и озвучиванием.").pack(anchor="w",pady=(2,10))
    listing=ttk.Treeview(f,columns=("when","text"),show="headings");listing.heading("when",text="Когда");listing.heading("text",text="Напомнить");listing.column("when",width=180);listing.column("text",width=480);listing.pack(fill="both",expand=True)
    def refresh():
        listing.delete(*listing.get_children())
        for i,(when,msg) in enumerate(list_reminders()):listing.insert("","end",iid=str(i),values=(when.strftime("%d.%m.%Y %H:%M"),msg))
    row=ttk.Frame(f);row.pack(fill="x",pady=8);value=tk.StringVar(master=win)
    ttk.Entry(row,textvariable=value).pack(side="left",fill="x",expand=True)
    def add():
        raw=value.get().strip()
        if not raw:return
        before=len(list_reminders());add_reminder(raw)
        if len(list_reminders())>before:value.set("");refresh()
        else:messagebox.showwarning("Напоминание","Не удалось распознать дату. Пример: завтра в 9 позвонить.",parent=win)
    ttk.Button(row,text="＋ Добавить",command=add).pack(side="left",padx=5)
    def remove():
        sel=listing.selection()
        if not sel:return
        if messagebox.askyesno("Удалить","Удалить выбранное напоминание?",parent=win):delete_reminder(int(sel[0]));refresh()
    ttk.Button(row,text="🗑 Удалить выбранное",command=remove).pack(side="left")
    refresh()
