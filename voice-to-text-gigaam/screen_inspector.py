"""Screen capture, OCR and visual understanding. No mouse or keyboard automation."""
from __future__ import annotations

import base64
import io
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from dialog_utils import center_window, apply_modern_style


def _prepare_image(image):
    """Resize large screenshots and return a JPEG data URL payload."""
    from PIL import Image
    prepared = image.convert("RGB")
    prepared.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    prepared.save(buffer, format="JPEG", quality=82, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _ask_screen_vision(image_data: str, question: str, ocr_text: str) -> str:
    """Send the current screenshot to the configured Ollama Cloud vision model."""
    prompt = (
        "Ты анализируешь актуальный снимок экрана Windows. Отвечай по-русски. "
        "Опирайся прежде всего на пиксели изображения; OCR ниже используй как подсказку. "
        "Не выдумывай невидимые элементы и не делай выводов о том, чего на снимке нет. "
        "Если часть текста мелкая или неразборчива, прямо укажи это. "
        "Не выполняй никаких действий и не предлагай нажимать кнопки как будто ты можешь "
        "управлять компьютером. Дай полезный текстовый ответ с кратким описанием окна, "
        "важного содержимого и ошибок, если они видны.\n\n"
        "Вопрос пользователя: " + question[:1500] +
        "\n\nТекст, распознанный локальным OCR:\n" + (ocr_text or "[Текст OCR не найден]")[:12000]
    )
    from ollama_client import chat
    return chat(
        [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": "data:image/jpeg;base64," + image_data},
        ]}],
        temperature=0.2,
        max_tokens=900,
        timeout=90,
    )


def open_screen_inspector(parent):
    win = tk.Toplevel(parent)
    apply_modern_style(win)
    win.title("GigaAM — анализ экрана")
    win.geometry("920x700")
    win.minsize(680, 500)
    center_window(win, parent)
    frame = ttk.Frame(win, padding=14)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="Анализ содержимого экрана", font=("Segoe UI", 17, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Снимок экрана → локальное распознавание текста → визуальный анализ ИИ. "
             "Помощник только читает и объясняет содержимое, не управляет компьютером.",
        wraplength=850,
    ).pack(anchor="w", pady=(3, 8))

    question = tk.StringVar(master=win, value="Опиши, что сейчас открыто на экране, и выдели важную информацию.")
    ttk.Entry(frame, textvariable=question).pack(fill="x", pady=6)
    output = tk.Text(frame, wrap="word", font=("Segoe UI", 10), padx=8, pady=8)
    output.pack(fill="both", expand=True)
    captured = {"image": None, "path": None}

    def show_status(text):
        if win.winfo_exists():
            output.delete("1.0", "end")
            output.insert("1.0", text)

    def capture():
        try:
            from PIL import ImageGrab
            captured["image"] = ImageGrab.grab(all_screens=True)
            captured["path"] = None
            show_status("Свежий снимок экрана готов. Задай вопрос и запусти анализ.")
        except Exception as exc:
            messagebox.showerror("Снимок экрана", str(exc), parent=win)

    def choose():
        path = filedialog.askopenfilename(
            parent=win,
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("Все файлы", "*.*")],
        )
        if path:
            try:
                from PIL import Image
                with Image.open(path) as source:
                    captured["image"] = source.copy()
                captured["path"] = path
                show_status("Изображение загружено. Задай вопрос и запусти анализ.")
            except Exception as exc:
                messagebox.showerror("Изображение", str(exc), parent=win)

    def analyze():
        image = captured["image"]
        if image is None:
            messagebox.showinfo("Экран", "Сначала сделай свежий снимок экрана или выбери изображение.", parent=win)
            return
        user_question = question.get().strip() or "Опиши содержимое изображения."
        if not messagebox.askyesno(
            "Передача снимка ИИ",
            "В Ollama Cloud будет отправлен снимок экрана целиком и распознанный текст. "
            "На снимке могут быть личные данные. Продолжить?",
            parent=win,
        ):
            return
        # Copy the image before starting the worker; UI widgets stay on the Tk thread.
        image_copy = image.copy()
        show_status("Распознаю текст локально и анализирую изображение…")

        def work():
            ocr_text = ""
            ocr_error = None
            vision_answer = None
            vision_error = None
            try:
                import pytesseract
                ocr_text = pytesseract.image_to_string(image_copy, lang="rus+eng").strip()
                if not ocr_text:
                    ocr_error = "OCR не обнаружил читаемого текста."
            except Exception as exc:
                ocr_error = "Локальный OCR недоступен: " + str(exc)
            try:
                image_data = _prepare_image(image_copy)
                vision_answer = _ask_screen_vision(image_data, user_question, ocr_text)
            except Exception as exc:
                vision_error = str(exc)

            sections = []
            if vision_answer:
                sections.append("АНАЛИЗ ИЗОБРАЖЕНИЯ\n" + vision_answer)
            else:
                sections.append("ВИЗУАЛЬНЫЙ АНАЛИЗ НЕ УДАЛСЯ\n" + (vision_error or "Неизвестная ошибка."))
            if ocr_text:
                sections.append("РАСПОЗНАННЫЙ ТЕКСТ\n" + ocr_text[:14000])
            elif ocr_error:
                sections.append("OCR\n" + ocr_error)
            result = "\n\n" + ("—" * 48) + "\n\n"
            result = result.join(sections)
            try:
                win.after(0, lambda: show_status(result))
            except tk.TclError:
                pass

        threading.Thread(target=work, daemon=True, name="screen-analysis").start()

    row = ttk.Frame(frame)
    row.pack(fill="x", pady=8)
    for label, command in [
        ("📸 Снимок экрана", capture),
        ("🖼 Открыть изображение…", choose),
        ("✨ Анализировать", analyze),
    ]:
        ttk.Button(row, text=label, command=command).pack(side="left", padx=(0, 6))
