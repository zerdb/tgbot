"""Simple RTSP camera viewer opened from the Other tools menu."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from dialog_utils import center_window


DEFAULT_CAMERA = "rtsp://admin@10.1.5.152:554"


def open_camera_viewer(parent):
    try:
        import cv2
        from PIL import Image, ImageTk
    except ImportError as exc:
        messagebox.showerror(
            "Просмотр камеры",
            "Не установлены компоненты просмотра видео. Выполните: python -m pip install -r requirements.txt",
            parent=parent,
        )
        return

    url = os.environ.get("GIGAAM_CAMERA_RTSP_URL", "").strip()
    if not url:
        from agent_core import get_camera_password
        camera_secret = get_camera_password()
        if not camera_secret:
            camera_secret = simpledialog.askstring(
                "Подключение к камере",
                "Введите пароль камеры (его можно сохранить в настройках):",
                show="*",
                parent=parent,
            )
        if camera_secret is None:
            return
        from urllib.parse import quote
        url = DEFAULT_CAMERA.replace("rtsp://admin@", "rtsp://admin:" + quote(camera_secret, safe="") + "@")

    win = tk.Toplevel(parent)
    win.title("GigaAM — просмотр камеры")
    win.geometry("960x600")
    win.minsize(640, 400)
    frame = ttk.Frame(win, padding=10)
    frame.pack(fill="both", expand=True)
    status = tk.StringVar(master=win, value="Подключаюсь к камере…")
    video_label = ttk.Label(frame, text="Ожидание видеопотока", anchor="center")
    video_label.pack(fill="both", expand=True)
    ttk.Label(frame, textvariable=status).pack(anchor="w", pady=(8, 0))

    frames = queue.Queue(maxsize=1)
    stop_event = threading.Event()
    capture_holder = {"capture": None}

    def publish(kind, payload):
        """Не блокирует поток чтения, даже если очередь кадров заполнена."""
        try:
            frames.put_nowait((kind, payload))
        except queue.Full:
            try:
                frames.get_nowait()
            except queue.Empty:
                pass
            try:
                frames.put_nowait((kind, payload))
            except queue.Full:
                pass

    def reader():
        # Владелец VideoCapture — только этот поток. Нельзя вызывать release()
        # из GUI-потока одновременно с capture.read(): это может уронить OpenCV.
        capture = None
        try:
            while not stop_event.is_set():
                try:
                    if capture is None or not capture.isOpened():
                        if capture is not None:
                            capture.release()
                        publish("status", "Подключаюсь к камере…")
                        capture = cv2.VideoCapture()
                        # Ограничиваем ожидание RTSP, если камера недоступна.
                        params = []
                        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                            params += [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000]
                        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                            params += [cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000]
                        opened = capture.open(url, cv2.CAP_FFMPEG, params) if params else capture.open(url, cv2.CAP_FFMPEG)
                        if not opened or not capture.isOpened():
                            publish("error", "Не удалось открыть RTSP-поток. Повтор подключения через 3 секунды…")
                            capture.release()
                            capture = None
                            if stop_event.wait(3):
                                break
                            continue

                    ok, image = capture.read()
                    if not ok or image is None:
                        publish("error", "Поток прервался. Переподключаюсь…")
                        capture.release()
                        capture = None
                        if stop_event.wait(2):
                            break
                        continue

                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    publish("frame", image)

                except cv2.error as exc:
                    publish("error", f"Ошибка OpenCV при чтении RTSP: {exc}. Переподключаюсь…")
                    if capture is not None:
                        try:
                            capture.release()
                        except Exception:
                            pass
                        capture = None
                    if stop_event.wait(2):
                        break
                except Exception as exc:
                    publish("error", f"Ошибка видеопотока: {exc}. Переподключаюсь…")
                    if capture is not None:
                        try:
                            capture.release()
                        except Exception:
                            pass
                        capture = None
                    if stop_event.wait(2):
                        break
        finally:
            if capture is not None:
                try:
                    capture.release()
                except Exception:
                    pass

    def update_image():
        if stop_event.is_set() or not win.winfo_exists():
            return
        try:
            kind, payload = frames.get_nowait()
            if kind in ("error", "status"):
                status.set(payload)
            else:
                image = Image.fromarray(payload)
                image.thumbnail((920, 510))
                photo = ImageTk.PhotoImage(image, master=win)
                video_label.configure(image=photo, text="")
                video_label.image = photo
                status.set("Камера подключена")
        except queue.Empty:
            pass
        win.after(30, update_image)

    def close():
        stop_event.set()
        # Освобождением VideoCapture занимается reader после выхода из read().
        # Параллельный release из Tk-потока способен аварийно завершить OpenCV.
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", close)
    center_window(win, parent)
    threading.Thread(target=reader, daemon=True, name="rtsp-camera-reader").start()
    win.after(30, update_image)
