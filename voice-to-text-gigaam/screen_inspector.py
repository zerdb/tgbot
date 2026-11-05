"""Screen capture and OCR assistant. OCR text is sent to the configured AI only after consent."""
from __future__ import annotations
import tkinter as tk, threading
from tkinter import ttk,messagebox,filedialog
from pathlib import Path
def open_screen_inspector(parent):
    win=tk.Toplevel(parent);win.title("GigaAM — понимание экрана");win.geometry("900x650");win.minsize(680,480)
    f=ttk.Frame(win,padding=14);f.pack(fill="both",expand=True)
    ttk.Label(f,text="Понимание экрана и изображений",font=("Segoe UI",17,"bold")).pack(anchor="w")
    ttk.Label(f,text="Снимок экрана или выбранного изображения → OCR → объяснение ИИ. Для OCR требуется установленный Tesseract и пакет pytesseract.").pack(anchor="w",pady=(3,8))
    question=tk.StringVar(master=win,value="Опиши, что изображено, и выдели важную информацию.")
    ttk.Entry(f,textvariable=question).pack(fill="x",pady=6)
    out=tk.Text(f,wrap="word",font=("Segoe UI",10));out.pack(fill="both",expand=True)
    captured={"image":None,"path":None}
    def capture():
        try:
            from PIL import ImageGrab
            captured["image"]=ImageGrab.grab(all_screens=True);captured["path"]=None
            out.delete("1.0","end");out.insert("1.0","Снимок экрана готов. Нажми «Распознать и объяснить».")
        except Exception as e:messagebox.showerror("Снимок экрана",str(e),parent=win)
    def choose():
        path=filedialog.askopenfilename(parent=win,filetypes=[("Изображения","*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),("Все файлы","*.*")])
        if path:
            try:
                from PIL import Image
                captured["image"]=Image.open(path);captured["path"]=path
                out.delete("1.0","end");out.insert("1.0","Изображение загружено: "+path)
            except Exception as e:messagebox.showerror("Изображение",str(e),parent=win)
    def analyze():
        image=captured["image"]
        if image is None:messagebox.showinfo("Экран","Сначала сделай снимок или выбери изображение.",parent=win);return
        if not messagebox.askyesno("Передача текста ИИ","OCR-текст с экрана будет отправлен в OpenRouter для анализа. Продолжить?",parent=win):return
        out.delete("1.0","end");out.insert("1.0","Распознаю текст…")
        def work():
            try:
                import pytesseract
                try: text=pytesseract.image_to_string(image,lang="rus+eng")
                except Exception as e: raise RuntimeError("Не удалось запустить Tesseract. Установи Tesseract OCR и языковые данные rus/eng. "+str(e))
                if not text.strip():raise RuntimeError("Текст не распознан. Проверь установку языковых данных Tesseract rus+eng.")
                from ai_chat import ask_ai
                answer=ask_ai("Ты помощник по анализу экрана. Отвечай только по распознанному тексту, явно отмечай предположения. Задача: "+question.get()+"\n\nOCR:\n"+text[:18000],remember=False)
                result="РАСПОЗНАННЫЙ ТЕКСТ:\n"+text[:12000]+"\n\nАНАЛИЗ ИИ:\n"+answer;err=None
            except Exception as e:result="";err=str(e)
            def done():out.delete("1.0","end");out.insert("1.0",result if not err else "Ошибка: "+err)
            win.after(0,done)
        threading.Thread(target=work,daemon=True).start()
    row=ttk.Frame(f);row.pack(fill="x",pady=8)
    for label,cmd in [("Снимок всего экрана",capture),("Открыть изображение…",choose),("Распознать и объяснить",analyze)]:
        ttk.Button(row,text=label,command=cmd).pack(side="left",padx=(0,6))
