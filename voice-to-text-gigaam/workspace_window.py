"""Single workspace for filename search, document content, folder sorting and web search."""
from __future__ import annotations
import tkinter as tk, threading, os, webbrowser
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
def open_workspace(parent):
    win=tk.Toplevel(parent);win.title("GigaAM — поиск и файлы");win.geometry("980x680");win.minsize(760,520)
    f=ttk.Frame(win,padding=14);f.pack(fill="both",expand=True)
    ttk.Label(f,text="Поиск и работа с файлами",font=("Segoe UI",17,"bold")).pack(anchor="w")
    folder=tk.StringVar(master=win,value=str(Path.home()/"Documents"));query=tk.StringVar(master=win);status=tk.StringVar(master=win,value="Выбери папку и введи запрос.")
    row=ttk.Frame(f);row.pack(fill="x",pady=8);ttk.Entry(row,textvariable=folder).pack(side="left",fill="x",expand=True)
    ttk.Button(row,text="Обзор…",command=lambda:folder.set(filedialog.askdirectory(parent=win) or folder.get())).pack(side="left",padx=5)
    ttk.Entry(f,textvariable=query).pack(fill="x",pady=(0,8))
    out=tk.Text(f,wrap="word",font=("Segoe UI",10));out.pack(fill="both",expand=True)
    def run(kind):
        q=query.get().strip()
        if not q: messagebox.showwarning("Поиск","Введи запрос.",parent=win);return
        status.set("Выполняю поиск…")
        def work():
            try:
                if kind=="name":
                    from file_indexer import refresh_and_search
                    result="\n".join(map(str,refresh_and_search(q)))
                elif kind=="content":
                    from document_search import _find_candidates
                    candidates=_find_candidates(Path(folder.get()).expanduser(),q)
                    if candidates:
                        from ai_chat import ask_ai
                        context="\n\n".join(f"Файл: {p}\n{c[:8000]}" for _,p,c in candidates)
                        result=ask_ai("Ответь на запрос только по содержимому документов, укажи источники. Запрос: "+q+"\n"+context[:24000],remember=False)
                        result+="\n\nИсточники:\n"+"\n".join(str(p) for _,p,_ in candidates)
                    else: result="Совпадений не найдено."
                else:
                    webbrowser.open("https://www.google.com/search?q="+__import__("urllib.parse",fromlist=["quote_plus"]).quote_plus(q));result="Поиск открыт в браузере."
                err=None
            except Exception as e:result="";err=str(e)
            def done():
                out.delete("1.0","end");out.insert("1.0",result if not err else "Ошибка: "+err);status.set("Готово." if not err else "Поиск завершился с ошибкой.")
            win.after(0,done)
        threading.Thread(target=work,daemon=True).start()
    buttons=ttk.Frame(f);buttons.pack(fill="x",pady=8)
    for label,kind in [("По имени (MFT)", "name"),("Внутри документов + ИИ","content"),("В интернете","web")]:
        ttk.Button(buttons,text=label,command=lambda k=kind:run(k)).pack(side="left",padx=(0,6))
    ttk.Button(buttons,text="Сортировка папки…",command=lambda:__import__("folder_organizer").open_folder_organizer(win)).pack(side="left")
    ttk.Label(f,textvariable=status).pack(anchor="w")
