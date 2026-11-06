"""Unified manager window for notes, tasks and reminders."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from dialog_utils import center_window, apply_modern_style

def open_reminders(parent):
    from reminders import list_items, add_note, add_reminder, update_item, complete_item, delete_item
    win=tk.Toplevel(parent); apply_modern_style(win)
    win.title("Zero Control — заметки и дела"); win.geometry("820x560"); win.minsize(620,400)
    center_window(win,parent)
    frame=ttk.Frame(win,padding=14); frame.pack(fill="both",expand=True)
    ttk.Label(frame,text="Заметки и дела",font=("Segoe UI",17,"bold")).pack(anchor="w")
    ttk.Label(frame,text="Одна запись может быть заметкой или делом со сроком. Выполненные записи сохраняются.",wraplength=760).pack(anchor="w",pady=(3,10))
    listing=ttk.Treeview(frame,columns=("status","due","text"),show="headings",selectmode="browse")
    listing.heading("status",text="Статус"); listing.heading("due",text="Напомнить"); listing.heading("text",text="Запись")
    listing.column("status",width=105,stretch=False); listing.column("due",width=155,stretch=False); listing.column("text",width=500)
    listing.pack(fill="both",expand=True)
    filter_var=tk.StringVar(master=win,value="Все")
    filter_row=ttk.Frame(frame); filter_row.pack(fill="x",pady=(8,4))
    ttk.Label(filter_row,text="Показать:").pack(side="left")
    filter_box=ttk.Combobox(filter_row,textvariable=filter_var,values=("Все","Активные","Выполненные"),state="readonly",width=14)
    filter_box.pack(side="left",padx=(5,12))
    item_map={}
    def refresh():
        listing.delete(*listing.get_children()); item_map.clear()
        for item in list_items(True):
            if filter_var.get()=="Активные" and item["completed"]: continue
            if filter_var.get()=="Выполненные" and not item["completed"]: continue
            due="—"
            if item.get("due_at"):
                try: due=datetime.fromisoformat(item["due_at"]).strftime("%d.%m.%Y %H:%M")
                except ValueError: due="Некорректная дата"
            status="Выполнено" if item["completed"] else ("Напоминание" if item.get("due_at") else "Заметка")
            listing.insert("","end",iid=item["id"],values=(status,due,item["text"])); item_map[item["id"]]=item
    def selected():
        ids=listing.selection()
        return item_map.get(ids[0]) if ids else None
    def edit_dialog(item=None):
        dialog=tk.Toplevel(win); apply_modern_style(dialog); dialog.title("Изменить запись" if item else "Новая запись")
        dialog.transient(win); dialog.grab_set(); dialog.geometry("540x320")
        body=ttk.Frame(dialog,padding=14); body.pack(fill="both",expand=True)
        ttk.Label(body,text="Текст заметки или дела").pack(anchor="w")
        text_box=tk.Text(body,height=6,wrap="word",font=("Segoe UI",10)); text_box.pack(fill="both",expand=True,pady=(4,10))
        if item: text_box.insert("1.0",item["text"])
        ttk.Label(body,text="Время напоминания (необязательно)").pack(anchor="w")
        due_var=tk.StringVar(master=dialog)
        if item and item.get("due_at"):
            try: due_var.set(datetime.fromisoformat(item["due_at"]).strftime("%d.%m.%Y %H:%M"))
            except ValueError: pass
        ttk.Entry(body,textvariable=due_var).pack(fill="x",pady=(4,3))
        ttk.Label(body,text="Примеры: «через 20 минут», «завтра в 9». Пустое поле — обычная заметка.").pack(anchor="w")
        row=ttk.Frame(body); row.pack(fill="x",pady=(12,0))
        def save():
            value=text_box.get("1.0","end").strip(); due=due_var.get().strip()
            if not value: messagebox.showwarning("Запись","Введи текст.",parent=dialog); return
            if due and not (due.startswith("через ") or due.startswith("завтра") or (len(due) == 16 and due[2] == "." and due[5] == ".")):
                messagebox.showwarning("Время","Используй «через 20 минут», «завтра в 9» или дату ДД.ММ.ГГГГ ЧЧ:ММ.",parent=dialog); return
            if item:
                ok=update_item(item["id"],value,due)
            elif due:
                ok=add_reminder("напомни "+due+" "+value)
            else: ok=add_note(value)
            if not ok:
                messagebox.showwarning("Запись","Не удалось сохранить запись или распознать срок.",parent=dialog); return
            dialog.destroy(); refresh()
        ttk.Button(row,text="Сохранить",command=save).pack(side="right")
        ttk.Button(row,text="Отмена",command=dialog.destroy).pack(side="right",padx=6)
        center_window(dialog,win); text_box.focus_set()
    def mark_done():
        item=selected()
        if not item: messagebox.showinfo("Выполнение","Сначала выбери запись.",parent=win); return
        if complete_item(item["id"]): refresh()
    def remove():
        item=selected()
        if not item: messagebox.showinfo("Удаление","Сначала выбери запись.",parent=win); return
        if messagebox.askyesno("Удалить","Удалить выбранную запись без возможности восстановления?",parent=win):
            delete_item(item["id"]); refresh()
    buttons=ttk.Frame(frame); buttons.pack(fill="x",pady=(5,0))
    ttk.Button(buttons,text="＋ Новая запись",command=lambda:edit_dialog()).pack(side="left")
    ttk.Button(buttons,text="Изменить",command=lambda:edit_dialog(selected()) if selected() else messagebox.showinfo("Изменение","Сначала выбери запись.",parent=win)).pack(side="left",padx=5)
    ttk.Button(buttons,text="✓ Выполнено",command=mark_done).pack(side="left")
    ttk.Button(buttons,text="Удалить",command=remove).pack(side="left",padx=5)
    ttk.Button(buttons,text="Обновить",command=refresh).pack(side="right")
    filter_box.bind("<<ComboboxSelected>>",lambda _e:refresh())
    listing.bind("<Double-1>",lambda _e:edit_dialog(selected()) if selected() else None)
    refresh()
