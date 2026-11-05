"""Simple local filename search and folder utilities."""
from __future__ import annotations
import os, tkinter as tk, threading, webbrowser
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from dialog_utils import center_window

def open_workspace(parent):
    win=tk.Toplevel(parent); win.title("GigaAM — файлы"); win.geometry("980x680"); win.minsize(760,520)
    frame=ttk.Frame(win,padding=14); frame.pack(fill="both",expand=True)
    ttk.Label(frame,text="⌕  Поиск файлов",font=("Segoe UI",17,"bold")).pack(anchor="w")
    folder=tk.StringVar(master=win,value=str(Path.home()))
    query=tk.StringVar(master=win)
    status=tk.StringVar(master=win,value="Выбери папку, введи часть имени файла и нажми «Найти».")
    row=ttk.Frame(frame); row.pack(fill="x",pady=8)
    ttk.Entry(row,textvariable=folder).pack(side="left",fill="x",expand=True)
    ttk.Button(row,text="📁  Обзор",command=lambda:folder.set(filedialog.askdirectory(parent=win) or folder.get())).pack(side="left",padx=5)
    ttk.Label(frame,text="Имя файла или его часть").pack(anchor="w")
    entry=ttk.Entry(frame,textvariable=query); entry.pack(fill="x",pady=(3,8))
    output=tk.Listbox(frame,font=("Segoe UI",10)); output.pack(fill="both",expand=True)
    found_paths=[]
    def search():
        root=Path(folder.get()).expanduser()
        term=query.get().strip().casefold()
        if not root.is_dir():
            messagebox.showwarning("Поиск","Выбери существующую папку.",parent=win); return
        if not term:
            messagebox.showwarning("Поиск","Введи имя или часть имени файла.",parent=win); return
        search_button.configure(state="disabled"); status.set("⌕  Ищу файлы во вложенных папках…")
        def worker():
            found=[]; skipped=0
            try:
                for current,dirs,names in os.walk(root):
                    dirs[:]=[d for d in dirs if d not in {"$RECYCLE.BIN","System Volume Information",".git",".venv","__pycache__"}]
                    for name in names:
                        if term in name.casefold():
                            found.append(str(Path(current)/name))
                            if len(found)>=500: break
                    if len(found)>=500: break
                error=None
            except Exception as exc: error=str(exc)
            def finish():
                if not win.winfo_exists(): return
                found_paths[:]=found; output.delete(0,"end")
                for path in found: output.insert("end",path)
                status.set(("Ошибка: "+error) if error else f"Найдено файлов: {len(found)}"+(" (показаны первые 500)" if len(found)>=500 else ""))
                search_button.configure(state="normal")
            win.after(0,finish)
        threading.Thread(target=worker,daemon=True,name="filename-search").start()
    def open_selected(_=None):
        selection=output.curselection()
        if not selection:return
        try: os.startfile(found_paths[selection[0]])
        except Exception as exc: messagebox.showerror("Открытие файла",str(exc),parent=win)
    output.bind("<Double-Button-1>",open_selected)
    search_button=ttk.Button(frame,text="⌕  Найти файлы",command=search); search_button.pack(anchor="w",pady=8)
    row2=ttk.Frame(frame); row2.pack(fill="x")
    ttk.Button(row2,text="🌐  Поиск в интернете",command=lambda: webbrowser.open("https://www.google.com/search?q="+__import__("urllib.parse",fromlist=["quote_plus"]).quote_plus(query.get().strip())) if query.get().strip() else None).pack(side="left",padx=(0,6))
    ttk.Button(row2,text="🗂  Сортировка папки",command=lambda:__import__("folder_organizer").open_folder_organizer(win)).pack(side="left")
    ttk.Label(frame,textvariable=status).pack(anchor="w",pady=(8,0))
    entry.bind("<Return>",lambda _e:search())
    center_window(win,parent)
