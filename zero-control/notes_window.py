"""Multimedia notes UI: text, local files, camera snapshots and clipboard images."""
from __future__ import annotations

import html
import os
import tempfile
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from urllib.parse import quote

from PIL import Image, ImageGrab, ImageTk

from agent_core import get_camera_password
from camera_window import DEFAULT_CAMERA
from dialog_utils import apply_modern_style, center_window
import notes_store


def open_notes_window(parent):
    win = tk.Toplevel(parent)
    apply_modern_style(win)
    win.title("Zero Control — мультимедийные заметки")
    win.geometry("1080x720")
    win.minsize(820, 560)

    shell = ttk.Frame(win, padding=12)
    shell.pack(fill="both", expand=True)
    ttk.Label(shell, text="Мультимедийные заметки",
              font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 10))

    content = ttk.Frame(shell)
    content.pack(fill="both", expand=True)
    sidebar = ttk.Frame(content, width=270)
    sidebar.pack(side="left", fill="y", padx=(0, 12))
    sidebar.pack_propagate(False)
    ttk.Label(sidebar, text="Мои заметки", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    note_list = tk.Listbox(sidebar, activestyle="none", font=("Segoe UI", 9),
                           relief="solid", borderwidth=1, exportselection=False)
    note_list.pack(fill="both", expand=True, pady=(6, 8))
    ttk.Button(sidebar, text="＋ Новая заметка", command=lambda: new_note()).pack(fill="x")

    editor = ttk.Frame(content)
    editor.pack(side="left", fill="both", expand=True)
    title_var = tk.StringVar(master=win)
    ttk.Label(editor, text="Заголовок").pack(anchor="w")
    title_entry = ttk.Entry(editor, textvariable=title_var, font=("Segoe UI", 11))
    title_entry.pack(fill="x", pady=(4, 9))
    ttk.Label(editor, text="Общий комментарий").pack(anchor="w")
    body = tk.Text(editor, height=7, wrap="word", font=("Segoe UI", 10),
                   undo=True, padx=8, pady=7)
    body.pack(fill="x", pady=(4, 10))

    attach_header = ttk.Frame(editor)
    attach_header.pack(fill="x")
    ttk.Label(attach_header, text="Вложения и комментарии",
              font=("Segoe UI", 10, "bold")).pack(side="left")
    ttk.Button(attach_header, text="＋ Файлы с компьютера",
               command=lambda: add_files()).pack(side="right")

    attach_area = ttk.Frame(editor)
    attach_area.pack(fill="both", expand=True, pady=(5, 5))
    attachment_list = tk.Listbox(attach_area, height=7, activestyle="none",
                                 font=("Segoe UI", 9), exportselection=False)
    attachment_list.pack(side="left", fill="both", expand=True)
    preview_label = ttk.Label(attach_area, text="Выбери изображение", anchor="center", width=34)
    preview_label.pack(side="right", fill="both", padx=(8, 0))
    attach_scroll = ttk.Scrollbar(attach_area, orient="vertical",
                                  command=attachment_list.yview)
    attach_scroll.pack(side="right", fill="y")
    attachment_list.configure(yscrollcommand=attach_scroll.set)

    caption_row = ttk.Frame(editor)
    caption_row.pack(fill="x", pady=(2, 7))
    caption_var = tk.StringVar(master=win)
    caption_entry = ttk.Entry(caption_row, textvariable=caption_var)
    caption_entry.pack(side="left", fill="x", expand=True)
    ttk.Button(caption_row, text="Сохранить комментарий",
               command=lambda: save_caption()).pack(side="left", padx=(6, 0))
    ttk.Button(caption_row, text="Удалить вложение",
               command=lambda: remove_attachment()).pack(side="left", padx=(6, 0))

    actions = ttk.Frame(editor)
    actions.pack(fill="x", pady=(5, 0))
    ttk.Button(actions, text="Вставить фото из буфера (Ctrl+V)",
               command=lambda: paste_image()).pack(side="left", padx=(0, 5))
    ttk.Button(actions, text="📷 Снимок с камеры",
               command=lambda: camera_snapshot()).pack(side="left", padx=5)
    ttk.Button(actions, text="Просмотр HTML",
               command=lambda: preview_html()).pack(side="right", padx=(5, 0))
    ttk.Button(actions, text="Удалить заметку",
               command=lambda: remove_note()).pack(side="right", padx=5)
    ttk.Button(actions, text="Сохранить",
               command=lambda: save_current()).pack(side="right", padx=5)

    state = {"note_id": None, "notes": [], "attachments": [], "selected_attachment": None}

    def refresh_notes(select_id=None):
        state["notes"] = notes_store.list_notes()
        note_list.delete(0, "end")
        selected_index = None
        for index, note in enumerate(state["notes"]):
            stamp = str(note.get("updated_at", ""))[:16].replace("T", " ")
            count = note.get("attachment_count", 0)
            note_list.insert("end", f"{note['title']}  ·  {count} 📎  ·  {stamp}")
            if note["id"] == select_id:
                selected_index = index
        if selected_index is not None:
            note_list.selection_set(selected_index)
            note_list.see(selected_index)

    def clear_editor():
        state["note_id"] = None
        state["attachments"] = []
        state["selected_attachment"] = None
        title_var.set("")
        body.delete("1.0", "end")
        caption_var.set("")
        attachment_list.delete(0, "end")
        preview_label.configure(image="", text="Выбери изображение")
        preview_label.image = None

    def load_note(note_id):
        note = notes_store.get_note(note_id)
        if not note:
            return
        state["note_id"] = note["id"]
        state["attachments"] = note["attachments"]
        state["selected_attachment"] = None
        title_var.set(note["title"])
        body.delete("1.0", "end")
        body.insert("1.0", note["body"])
        caption_var.set("")
        attachment_list.delete(0, "end")
        for item in state["attachments"]:
            attachment_list.insert("end", f"{item['filename']}  —  {item.get('caption', '')}")
        preview_label.configure(image="", text="Выбери изображение")
        preview_label.image = None
        title_entry.focus_set()

    def new_note():
        clear_editor()
        title_var.set("Новая заметка")
        title_entry.focus_set()
        note_list.selection_clear(0, "end")

    def save_current():
        note_id = notes_store.save_note(
            state["note_id"], title_var.get(), body.get("1.0", "end-1c")
        )
        state["note_id"] = note_id
        refresh_notes(note_id)
        return note_id

    def add_source(path):
        note_id = save_current()
        notes_store.add_attachment(note_id, path)
        load_note(note_id)
        refresh_notes(note_id)

    def add_files():
        paths = filedialog.askopenfilenames(
            parent=win, title="Добавить файлы в заметку",
            filetypes=[("Все файлы", "*.*"), ("Изображения", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff")],
        )
        if not paths:
            return
        try:
            note_id = save_current()
            for path in paths:
                notes_store.add_attachment(note_id, path)
            load_note(note_id)
            refresh_notes(note_id)
        except Exception as exc:
            messagebox.showerror("Вложения", f"Не удалось добавить файл: {exc}", parent=win)

    def paste_image(event=None):
        try:
            clipboard = ImageGrab.grabclipboard()
            if isinstance(clipboard, Image.Image):
                notes_store.ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    suffix=".png", dir=notes_store.ATTACHMENTS_DIR, delete=False
                ) as temp:
                    temp_path = Path(temp.name)
                try:
                    clipboard.convert("RGB").save(temp_path, format="PNG")
                    add_source(temp_path)
                finally:
                    temp_path.unlink(missing_ok=True)
                return "break"
            if isinstance(clipboard, list):
                paths = [p for p in clipboard if isinstance(p, str) and Path(p).is_file()]
                if paths:
                    note_id = save_current()
                    for path in paths:
                        notes_store.add_attachment(note_id, path)
                    load_note(note_id)
                    refresh_notes(note_id)
                    return "break"
            # Не перехватываем обычный текст: Ctrl+V в полях редактора остаётся стандартной вставкой.
            return None
        except Exception as exc:
            messagebox.showerror("Буфер обмена", str(exc), parent=win)
            return "break"

    def camera_snapshot():
        try:
            import cv2
            url = os.environ.get(
                "ZERO_CONTROL_CAMERA_RTSP_URL",
                os.environ.get("GIGAAM_CAMERA_RTSP_URL", ""),
            ).strip()
            if not url:
                password = get_camera_password()
                if not password:
                    password = simpledialog.askstring(
                        "Подключение к камере",
                        "Введите пароль камеры (его можно сохранить в настройках):",
                        show="*", parent=win,
                    )
                if password is None:
                    return
                url = DEFAULT_CAMERA.replace(
                    "rtsp://admin@",
                    "rtsp://admin:" + quote(password, safe="") + "@",
                )
            capture = cv2.VideoCapture()
            params = []
            if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                params += [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000]
            if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                params += [cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000]
            opened = capture.open(url, cv2.CAP_FFMPEG, params) if params else capture.open(url, cv2.CAP_FFMPEG)
            if not opened or not capture.isOpened():
                capture.release()
                raise RuntimeError("Не удалось подключиться к камере.")
            ok, frame = capture.read()
            capture.release()
            if not ok or frame is None:
                raise RuntimeError("Камера не передала кадр.")
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            notes_store.ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                suffix=".jpg", dir=notes_store.ATTACHMENTS_DIR, delete=False
            ) as temp:
                temp_path = Path(temp.name)
            try:
                image.save(temp_path, format="JPEG", quality=92)
                add_source(temp_path)
            finally:
                temp_path.unlink(missing_ok=True)
        except Exception as exc:
            messagebox.showerror("Снимок с камеры", str(exc), parent=win)

    def selected_attachment():
        selection = attachment_list.curselection()
        if not selection:
            return None
        index = selection[0]
        if index >= len(state["attachments"]):
            return None
        return state["attachments"][index]

    def on_attachment_select(_event=None):
        item = selected_attachment()
        state["selected_attachment"] = item["id"] if item else None
        caption_var.set(item.get("caption", "") if item else "")
        preview_label.configure(image="", text="Файл без предпросмотра")
        preview_label.image = None
        if item and item.get("mime_type", "").startswith("image/"):
            try:
                with Image.open(item["path"]) as source:
                    image = source.copy()
                image.thumbnail((340, 280))
                photo = ImageTk.PhotoImage(image, master=win)
                preview_label.configure(image=photo, text="")
                preview_label.image = photo
            except Exception:
                preview_label.configure(text="Не удалось открыть изображение")

    def save_caption():
        item = selected_attachment()
        if not item:
            messagebox.showinfo("Комментарий", "Сначала выбери вложение.", parent=win)
            return
        notes_store.update_attachment_caption(item["id"], caption_var.get())
        note_id = state["note_id"]
        load_note(note_id)
        refresh_notes(note_id)
        index = next((i for i, x in enumerate(state["attachments"]) if x["id"] == item["id"]), None)
        if index is not None:
            attachment_list.selection_set(index)

    def remove_attachment():
        item = selected_attachment()
        if not item:
            messagebox.showinfo("Вложение", "Сначала выбери вложение.", parent=win)
            return
        if not messagebox.askyesno(
            "Удалить вложение",
            f"Удалить файл «{item['filename']}» из этой заметки?",
            parent=win,
        ):
            return
        notes_store.delete_attachment(item["id"])
        note_id = state["note_id"]
        load_note(note_id)
        refresh_notes(note_id)

    def remove_note():
        note_id = state["note_id"]
        if not note_id:
            return
        if not messagebox.askyesno(
            "Удалить заметку",
            "Удалить заметку и все её вложения с диска? Это действие нельзя отменить.",
            parent=win,
        ):
            return
        notes_store.delete_note(note_id)
        clear_editor()
        refresh_notes()

    def preview_html():
        note_id = save_current()
        note = notes_store.get_note(note_id)
        preview_dir = notes_store.APP_DATA / "html_previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        blocks = []
        for item in note["attachments"]:
            path = Path(item["path"])
            caption = html.escape(item.get("caption", ""))
            filename = html.escape(item["filename"])
            if item["mime_type"].startswith("image/"):
                source = path.resolve().as_uri()
                media = f'<img src="{source}" alt="{filename}">'
            else:
                media = f'<p class="file">📎 {filename}</p>'
            blocks.append(f'<figure>{media}<figcaption>{caption}</figcaption></figure>')
        body_html = html.escape(note["body"]).replace("\n", "<br>") 
        document = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(note['title'])}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:40px auto;padding:0 22px;color:#172033;line-height:1.6;background:#f5f6fa}}
article{{background:white;padding:30px;border-radius:16px;box-shadow:0 4px 24px #17203312}}
h1{{margin-top:0}} .body{{white-space:normal;margin-bottom:24px}} figure{{margin:22px 0;padding:14px;background:#f7f8fc;border-radius:12px}}
img{{display:block;max-width:100%;max-height:680px;object-fit:contain;margin:auto;border-radius:8px}}
figcaption{{margin-top:10px;color:#536078}} .file{{overflow-wrap:anywhere}}
</style></head><body><article><h1>{html.escape(note['title'])}</h1>
<div class="body">{body_html}</div>{''.join(blocks)}</article></body></html>"""
        destination = preview_dir / f"{note_id}.html"
        destination.write_text(document, encoding="utf-8")
        webbrowser.open(destination.as_uri())

    note_list.bind("<<ListboxSelect>>", lambda _event: (
        load_note(state["notes"][note_list.curselection()[0]]["id"])
        if note_list.curselection() else None
    ))
    attachment_list.bind("<<ListboxSelect>>", on_attachment_select)
    win.bind_all("<Control-v>", paste_image)
    win.bind_all("<Control-V>", paste_image)

    def close():
        try:
            win.unbind_all("<Control-v>")
            win.unbind_all("<Control-V>")
        except tk.TclError:
            pass
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", close)
    refresh_notes()
    if state["notes"]:
        note_list.selection_set(0)
        load_note(state["notes"][0]["id"])
    else:
        new_note()
    center_window(win, parent)
