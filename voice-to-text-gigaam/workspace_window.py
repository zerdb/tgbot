"""Local workspace for filename/content search, folder sorting and web search."""
from __future__ import annotations
import tkinter as tk, threading, webbrowser
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

def open_workspace(parent):
    win=tk.Toplevel(parent); win.title("GigaAM — поиск и файлы"); win.geometry("980x680"); win.minsize(760,520)
    frame=ttk.Frame(win,padding=14); frame.pack(fill="both",expand=True)
    ttk.Label(frame,text="Поиск и работа с файлами",font=("Segoe UI",17,"bold")).pack(anchor="w")
    folder=tk.StringVar(master=win,value=str(Path.home()/"Documents"))
    query=tk.StringVar(master=win)
    status=tk.StringVar(master=win,value="Выбери папку и введи запрос.")
    row=ttk.Frame(frame); row.pack(fill="x",pady=8)
    ttk.Entry(row,textvariable=folder).pack(side="left",fill="x",expand=True)
    ttk.Button(row,text="Обзор…",command=lambda:folder.set(filedialog.askdirectory(parent=win) or folder.get())).pack(side="left",padx=5)
    ttk.Entry(frame,textvariable=query).pack(fill="x",pady=(0,8))
    output=tk.Text(frame,wrap="word",font=("Segoe UI",10)); output.pack(fill="both",expand=True)
    def run(kind):
        q=query.get().strip()
        if not q:
            messagebox.showwarning("Поиск","Введи запрос.",parent=win); return
        selected_folder=Path(folder.get()).expanduser()
        if kind=="content" and not selected_folder.is_dir():
            messagebox.showwarning("Поиск","Выбери существующую папку.",parent=win); return
        status.set("Выполняю поиск…")
        def worker():
            try:
                if kind=="name":
                    from file_indexer import refresh_and_search
                    found=refresh_and_search(q)
                    result="\n".join(map(str,found)) if found else "Файлы не найдены."
                elif kind=="content":
                    from document_search import _find_candidates
                    candidates=_find_candidates(selected_folder,q)
                    if candidates:
                        chunks=[f"Файл: {path}\nСовпадений: {score}\nФрагмент:\n{content[:2500]}" for score,path,content in candidates]
                        result=f"Найдено документов: {len(candidates)}\n\n"+"\n\n".join(chunks)
                    else: result="Совпадений в поддерживаемых документах не найдено."
                else:
                    from urllib.parse import quote_plus
                    webbrowser.open("https://www.google.com/search?q="+quote_plus(q))
                    result="Поиск открыт в браузере."
                error=None
            except Exception as exc:
                result=""; error=str(exc)
            def finish():
                if not win.winfo_exists(): return
                output.delete("1.0","end")
                output.insert("1.0",result if not error else "Ошибка: "+error)
                status.set("Готово." if not error else "Поиск завершился с ошибкой.")
            win.after(0,finish)
        threading.Thread(target=worker,daemon=True).start()
    buttons=ttk.Frame(frame); buttons.pack(fill="x",pady=8)
    for label,kind in [("Поиск по имени","name"),("Поиск по содержимому","content"),("В интернете","web")]:
        ttk.Button(buttons,text=label,command=lambda k=kind:run(k)).pack(side="left",padx=(0,6))
    ttk.Button(buttons,text="Сортировка папки…",command=lambda:__import__("folder_organizer").open_folder_organizer(win)).pack(side="left")
    ttk.Label(frame,textvariable=status).pack(anchor="w")
