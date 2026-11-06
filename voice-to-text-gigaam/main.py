"""Zero Control — офлайн голосовой помощник для Windows."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import queue
import time
import traceback
import webbrowser
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta
from pathlib import Path

import tkinter as tk

# Показываем заставку до импорта модулей приложения.
_splash = tk.Tk()
_splash.overrideredirect(True)
_splash.attributes("-topmost", True)
_splash.attributes("-alpha", 0.96)
_splash.configure(bg="#202124")
_splash_frame = tk.Frame(_splash, bg="#202124", padx=16, pady=10)
_splash_frame.pack()
tk.Label(_splash_frame, text="⏳", font=("Segoe UI Emoji", 22), fg="#fbbc04", bg="#202124").pack(side="left", padx=(0, 9))
tk.Label(_splash_frame, text="Загружается помощник…", font=("Segoe UI", 10, "bold"), fg="white", bg="#202124").pack(side="left")
_splash.update_idletasks()
_splash_width, _splash_height = _splash.winfo_reqwidth(), _splash.winfo_reqheight()
_splash_x = _splash.winfo_screenwidth() - _splash_width - 24
_splash_y = (_splash.winfo_screenheight() - _splash_height) // 2
_splash.geometry(f"+{_splash_x}+{_splash_y}")
_splash.update_idletasks()
_splash.update()

from windows_actions import lock_computer, reboot_computer, open_downloads, open_recycle_bin, open_application, open_settings, empty_recycle_bin, take_screenshot, paste_clipboard_to_excel, save_clipboard_as_note
from reminders import start_reminder_service, stop_reminder_service, add_reminder, add_note, complete_item_by_text, deliver_due_reminders
from file_search import search_web, search_files, start_file_search_ui
from email_form import open_email_form
from contact_form import open_contact_form
from folder_organizer import open_folder_organizer
from assistant_window import AssistantWindow, show_ai_answer
from ai_chat import ask_ai
from mail_client import open_mail_client
from workspace_window import open_workspace
from reminders_window import open_reminders
from screen_inspector import open_screen_inspector
from camera_window import open_camera_viewer

_ui = None  # GUI создаётся позже, после загрузки модулей
_STARTUP_TIME = time.perf_counter()


def progress(message: str):
    """Обновляет фирменную плавающую плашку справа по центру экрана."""
    global _ui
    if _ui is None:
        return
    try:
        _ui.set_busy_overlay(message)
        # На старте тяжёлая загрузка модели временно занимает главный поток.
        # Обрабатываем очередь Tk немедленно, чтобы плашка реально успела появиться.
        _ui.root.update_idletasks()
        _ui.root.update()
    except Exception:
        pass




SAMPLE_RATE = 16000
CHANNELS = 1
MAX_CHUNK_SECONDS = 24

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
VK_RSHIFT, VK_RCONTROL = 0xA1, 0xA3
_pressed_physical_right = set()
_keyboard_events = queue.SimpleQueue()
_keyboard_hook = None
_keyboard_hook_proc = None

PROJECT_DIR = Path(__file__).resolve().parent
MODEL_DIR = Path(os.getenv("GIGAAM_MODEL_DIR", str(PROJECT_DIR.parent / "GigaAM-v3"))).expanduser().resolve()
SCREENSHOT_DIR = PROJECT_DIR / "Скриншоты"

_model = None
_stream = None
_audio_chunks: list[np.ndarray] = []
_recording = False
_recording_mode = "text"
_lock = threading.Lock()
_transcription_lock = threading.Lock()
_ui = None
_ui_actions = queue.SimpleQueue()


def update_ui_status(listening=None, recording=None):
    if _ui is not None:
        _ui.set_status(listening=listening)
        if recording is not None:
            _ui.set_recording_overlay(bool(recording), mode=recording if recording else None)


def configure_ffmpeg():
    source = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    target_dir = Path(tempfile.gettempdir()) / "gigaam_ffmpeg"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "ffmpeg.exe"
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        shutil.copy2(source, target)
    os.environ["PATH"] = str(target_dir) + os.pathsep + os.environ.get("PATH", "")



def check_microphone() -> bool:
    try:
        device = sd.query_devices(kind="input")
        if device["max_input_channels"] < CHANNELS:

            return False
    except (sd.PortAudioError, OSError) as exc:

        return False

    return True


def load_model():
    global _model
    if not (MODEL_DIR / "config.json").is_file():
        raise FileNotFoundError(
            f"Локальная модель GigaAM не найдена: {MODEL_DIR}\n"
            "Поместите модель ai-sage/GigaAM-v3 (revision e2e_rnnt) "
            "в папку GigaAM-v3 рядом с voice-to-text-gigaam."
        )

    _model = AutoModel.from_pretrained(str(MODEL_DIR), trust_remote_code=True, local_files_only=True)
    _model.eval()



def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Состояние аудиоустройства: {status}")
    with _lock:
        if _recording:
            _audio_chunks.append(indata.copy())


def start_recording(mode: str):
    global _stream, _recording, _recording_mode, _audio_chunks
    with _lock:
        if _recording:
            return
        _audio_chunks = []
        _recording_mode = mode
        _recording = True
    try:
        # Сначала мгновенно показываем уже подготовленную плашку, затем запускаем аудиопоток.
        update_ui_status("ИДЁТ ДИКТОВКА" if mode == "text" else "СЛУШАЮ ГОЛОСОВУЮ КОМАНДУ", recording=mode)
        if _ui is not None:
            _ui.root.update_idletasks()
            _ui.root.update()
        _stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", callback=audio_callback)
        _stream.start()
        key_name = "Right Ctrl+Right Shift" if mode == "text" else "правый Ctrl"
        purpose = "для ввода текста" if mode == "text" else "для голосовой команды"
        print(f"Идёт запись {purpose}. Отпустите {key_name}, чтобы выполнить.")
    except (sd.PortAudioError, OSError) as exc:
        with _lock:
            _recording = False
        _stream = None
        print(f"Не удалось начать запись: {exc}")
        update_ui_status("ОШИБКА ЗАПИСИ", recording=False)


def promote_to_dictation():
    """If Right Shift joins an active Right Ctrl recording, switch to dictation."""
    global _recording_mode
    with _lock:
        if not _recording or _recording_mode == "text":
            return
        _recording_mode = "text"
    print("Режим переключён на диктовку: удерживайте Right Ctrl + Right Shift.")
    update_ui_status("ДИКТОВКА", recording="text")


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]

HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD
)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (
    wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

def _native_keyboard_event(n_code, w_param, l_param):
    # Не запускаем запись и не трогаем состояние приложения из системного callback.
    # Только передаём событие в очередь для обработки главным потоком Tkinter.
    if n_code >= 0 and w_param in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
        try:
            vk = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
            if vk in (VK_RCONTROL, VK_RSHIFT):
                _keyboard_events.put((vk, w_param))
        except Exception:
            pass
    return user32.CallNextHookEx(_keyboard_hook, n_code, w_param, l_param)


def process_keyboard_events():
    """Обрабатывает физические Right Ctrl/Shift только в главном потоке GUI."""
    while True:
        try:
            vk, event = _keyboard_events.get_nowait()
        except queue.Empty:
            break

        if event in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if vk in _pressed_physical_right:
                continue
            _pressed_physical_right.add(vk)
            if vk == VK_RCONTROL:
                start_recording("text" if VK_RSHIFT in _pressed_physical_right else "command")
            elif VK_RCONTROL in _pressed_physical_right:
                with _lock:
                    active = _recording
                if active:
                    promote_to_dictation()
        else:
            _pressed_physical_right.discard(vk)
            if vk == VK_RSHIFT:
                with _lock:
                    should_stop = _recording and _recording_mode == "text"
                if should_stop:
                    stop_recording()
            elif vk == VK_RCONTROL:
                stop_recording()

def install_right_only_keyboard_hook():
    global _keyboard_hook, _keyboard_hook_proc
    _keyboard_hook_proc = HOOKPROC(_native_keyboard_event)
    # For WH_KEYBOARD_LL, use a null module handle for this in-process callback.
    _keyboard_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _keyboard_hook_proc, None, 0)
    if not _keyboard_hook:
        raise ctypes.WinError(ctypes.get_last_error())


def remove_keyboard_hook():
    global _keyboard_hook, _keyboard_hook_proc
    if _keyboard_hook:
        user32.UnhookWindowsHookEx(_keyboard_hook)
        _keyboard_hook = None
    _keyboard_hook_proc = None
    _pressed_physical_right.clear()

def stop_recording():
    global _stream, _recording
    with _lock:
        if not _recording:
            return
        _recording = False
        chunks = list(_audio_chunks)
        mode = _recording_mode
    stream, _stream = _stream, None
    if stream is not None:
        try:
            stream.stop()
        finally:
            stream.close()
    update_ui_status("РАСПОЗНАЮ РЕЧЬ", recording=False)
    if not chunks:
        print("Звук не записан: микрофон не передал аудиоданные.")
        update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
        return
    audio_data = np.concatenate(chunks, axis=0).reshape(-1)
    if audio_data.size == 0:
        print("Звук не записан.")
        return
    print(f"Запись завершена: {len(audio_data) / SAMPLE_RATE:.2f} сек.")
    worker = transcribe_and_paste if mode == "text" else transcribe_and_execute
    threading.Thread(target=worker, args=(audio_data,), daemon=True).start()


def transcribe_audio_file(audio_data: np.ndarray) -> str:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = Path(tmp.name)
        sf.write(str(temp_path), audio_data, SAMPLE_RATE, subtype="PCM_16")
        with torch.inference_mode():
            return _model.transcribe(str(temp_path)).strip()
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def transcribe_parts(audio_data: np.ndarray, label: str) -> str:
    chunk_size = SAMPLE_RATE * MAX_CHUNK_SECONDS
    parts = [audio_data[i:i + chunk_size] for i in range(0, len(audio_data), chunk_size)]
    results = []
    for index, part in enumerate(parts, start=1):
        if len(parts) > 1:
            print(f"Распознаю {label} {index} из {len(parts)}...")
        result = transcribe_audio_file(part)
        if result:
            results.append(result)
    return " ".join(results).strip()


def transcribe_and_paste(audio_data: np.ndarray):
    if not _transcription_lock.acquire(blocking=False):
        print("Предыдущее распознавание ещё выполняется. Эта запись пропущена.")
        return
    try:
        print("Распознаю речь локально...")
        text = transcribe_parts(audio_data, "фрагмент")
        if text:
            pyperclip.copy(text)
            keyboard.send("ctrl+v")
            print(f"Текст распознан и вставлен: {text}")
        else:
            print("Речь не распознана.")
    except Exception as exc:
        print(f"Ошибка распознавания: {exc}")
        traceback.print_exc()
    finally:
        _transcription_lock.release()
        update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")


def normalize_command(text: str) -> str:
    normalized = text.lower().replace("ё", "е")
    normalized = re.sub(r"[^а-яa-z0-9.:/ -]+", " ", normalized)
    # ASR often adds a final period or comma; it must not break exact commands.
    return " ".join(normalized.split()).strip(" .,:;!?")


def handle_command(text: str):
    """Единая точка входа: сразу показывает статус, затем определяет намерение."""
    print(f"Распознана команда: {text}")
    # Команда уже распознана: не ждём ответа классификатора, чтобы показать индикатор.
    if _ui is not None:
        _ui.set_busy_overlay("Обрабатываю команду…")
    try:
        from intent_router import understand_command
        intent = understand_command(text)
    except Exception as exc:
        if _ui is not None:
            _ui.set_busy_overlay(None)
        print(f"Ollama Cloud не смог обработать команду: {exc}")
        print("Команда не выполнена. Проверьте интернет и наличие ключа Ollama Cloud в настройках.")
        return
    action = intent.get("action", "unknown")
    args = intent.get("arguments") or {}
    confidence = float(intent.get("confidence", 0) or 0)
    if action == "unknown" or confidence < 0.55:
        if _ui is not None:
            _ui.set_busy_overlay(None)
        print("Не совсем понял задачу. Повтори её другими словами.")
        return
    print(f"Понял намерение: {action} (уверенность {confidence:.2f})")
    parent = _ui.root if _ui is not None else None
    keep_busy = action in ("search_files", "ai_chat", "read_unread_mail", "inspect_camera_image", "camera_question")
    if action == "ai_chat":
        question = str(args.get("question") or text).strip()
        if _ui is not None:
            _ui.set_busy_overlay("Жду ответ ИИ…")
        _ui_actions.put(("ai_chat", question))
    elif action in ("add_contact", "open_contacts"):
        print("[GUI] Открываю общую адресную книгу.", flush=True)
        # Для голосового «добавь в контакты» открываем ту же книгу сразу
        # с пустой карточкой; «открой контакты» показывает список.
        _ui_actions.put(("add_contact", action == "add_contact"))
    elif action == "email_compose":
        _ui_actions.put(("email_compose", bool(args.get("attach_copied_files", False))))
    elif action == "inspect_camera_image":
        _ui_actions.put(("inspect_camera_image", None))
    elif action == "camera_question":
        _ui_actions.put(("camera_question", str(args.get("question") or text).strip()))
    elif action == "open_assistant_settings":
        _ui_actions.put((action, None))
    elif action == "open_reminders":
        _ui_actions.put(("open_reminders", None))
    elif action == "open_mail_client":
        _ui_actions.put(("open_mail_client", None))
    elif action == "read_unread_mail":
        _ui_actions.put(("confirm_read_mail", None))
    elif action == "save_note": save_clipboard_as_note()
    elif action == "clipboard_to_excel": paste_clipboard_to_excel()
    elif action == "lock_computer": lock_computer()
    elif action == "reboot_computer": reboot_computer()
    elif action == "open_downloads": open_downloads()
    elif action == "open_recycle_bin": open_recycle_bin()
    elif action == "open_application": open_application(str(args.get("app") or ""))
    elif action == "open_settings": open_settings()
    elif action == "empty_recycle_bin": empty_recycle_bin()
    elif action == "screenshot": take_screenshot()
    elif action == "reminder": add_reminder(str(args.get("reminder_text") or text))
    elif action == "add_note": add_note(str(args.get("note_text") or text))
    elif action == "complete_item":
        if not complete_item_by_text(str(args.get("item_text") or "")):
            print("Не нашёл подходящую активную запись. Открой заметки и дела, чтобы выбрать её.")
    elif action == "organize_folder": open_folder_organizer(parent)
    elif action == "search_web": search_web(str(args.get("query") or text))
    elif action == "search_files":
        if _ui is not None:
            _ui.set_busy_overlay("Ищу файлы…")
        search_files(str(args.get("query") or text), parent)
    else:
        print("Эта операция пока не подключена.")
    if not keep_busy and _ui is not None:
        _ui.set_busy_overlay(None)

def transcribe_and_execute(audio_data: np.ndarray):
    if not _transcription_lock.acquire(blocking=False):
        print("Предыдущее распознавание ещё выполняется. Эта запись пропущена.")
        return
    try:
        print("Распознаю голосовую команду...")
        text = transcribe_parts(audio_data, "фрагмент команды")
        if text:
            try:
                handle_command(text)
            except Exception as exc:
                print(f"Ошибка выполнения команды: {exc}")
                traceback.print_exc()
        else:
            print("Голосовая команда не распознана.")
    except Exception as exc:
        print(f"Ошибка распознавания команды: {exc}")
        traceback.print_exc()
    finally:
        _transcription_lock.release()
        update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")


def _ask_ai_worker(question: str):
    try:
        answer = ask_ai(question)
        result = (question, answer, None)
    except Exception as exc:
        result = (question, None, str(exc))
    _ui_actions.put(("ai_chat_result", result))


def _camera_inspection_worker():
    try:
        from camera_inspector import inspect_camera
        from notifications import speak_text as speak
        present = inspect_camera()
        if present:
            speak("Начальник есть")
            result = ("Начальник есть", None)
        else:
            speak("Начальника нет")
            result = ("Начальника нет", None)
    except Exception as exc:
        result = ("", str(exc))
    _ui_actions.put(("camera_inspection_result", result))

def _camera_question_worker(question: str):
    try:
        from camera_inspector import inspect_camera_question
        from notifications import speak_text as speak
        answer = inspect_camera_question(question)
        speak(answer)
        result = (question, answer, None)
    except Exception as exc:
        result = (question, None, str(exc))
    _ui_actions.put(("camera_question_result", result))


def _mail_reader_worker():
    try:
        from mail_reader import summarize_unread
        answer = summarize_unread()
        result = ("Сводка непрочитанных писем", answer, None)
    except Exception as exc:
        result = ("Сводка непрочитанных писем", None, str(exc))
    _ui_actions.put(("ai_chat_result", result))


def main():
    global _ui, imageio_ffmpeg, keyboard, np, pyperclip, sd, sf, ImageGrab, audio, torch, AutoModel

    # Заставка уже показана до импорта модулей приложения.
    # Долгая загрузка проходит за заставкой; главное окно пока не открываем.
    import imageio_ffmpeg
    import keyboard
    import numpy as np
    import pyperclip
    import sounddevice as sd
    import soundfile as sf
    from PIL import ImageGrab
    from winotify import audio
    import torch
    from transformers import AutoModel
    from notifications import initialize_speech_engine

    # Загружаем Piper и голос Денис заранее в фоновом потоке.
    # Интерфейс и загрузка GigaAM не ждут завершения этой операции.
    initialize_speech_engine()

    _ui = AssistantWindow(
        on_close=shutdown,
        on_command=handle_command,
        microphone_status="ПРОВЕРКА",
        on_open_mail=lambda: open_mail_client(_ui.root),
        on_open_files=lambda: open_workspace(_ui.root),
        on_open_reminders=lambda: open_reminders(_ui.root),
        on_open_screen=lambda: open_screen_inspector(_ui.root),
        on_open_other=lambda: open_camera_viewer(_ui.root),
    )
    # Сначала создаём и отображаем главное окно, затем убираем заставку —
    # между ними не должно быть пустой паузы.
    _ui.root.update_idletasks()
    _ui.root.update()
    _splash.destroy()

    microphone_found = check_microphone()
    _ui.set_status(microphone="НАЙДЕН" if microphone_found else "НЕ НАЙДЕН")
    configure_ffmpeg()
    load_model()
    _ui.set_busy_overlay(None)
    install_right_only_keyboard_hook()
    start_file_search_ui(_ui.root, busy_callback=_ui.set_busy_overlay)
    # Таймер очереди напоминаний обслуживается главным потоком Tkinter.
    start_reminder_service()

    def process_background_events():
        # Сначала гарантируем следующий запуск опроса: ошибка любого обработчика
        # не должна навсегда остановить очередь GUI-действий.
        try:
            _ui.root.after(25, process_background_events)
        except Exception:
            return

        try:
            process_keyboard_events()
        except Exception:
            print("[GUI] Ошибка обработки клавиатурных событий:", flush=True)
            traceback.print_exc()

        while True:
            try:
                ui_action, value = _ui_actions.get_nowait()
            except queue.Empty:
                break

            print(f"[GUI] Получено действие из очереди: {ui_action}", flush=True)
            try:
                if ui_action == "add_contact":
                    print("[GUI] Открываю адресную книгу.", flush=True)
                    open_contact_form(parent=_ui.root, start_new=bool(value))
                    print("[GUI] Вызов адресной книги завершён.", flush=True)
                elif ui_action == "email_compose":
                    print("[GUI] Открываю окно нового письма.", flush=True)
                    open_email_form(parent=_ui.root, add_files_on_open=value)
                    print("[GUI] Вызов формы письма завершён.", flush=True)
                elif ui_action == "camera_question":
                    _ui.set_busy_overlay("Получаю кадр и анализирую вопрос…")
                    threading.Thread(target=_camera_question_worker, args=(str(value or ""),), daemon=True, name="camera-question").start()
                elif ui_action == "camera_question_result":
                    _ui.set_busy_overlay(None)
                    question, answer, error = value
                    if error:
                        print("[Камера] " + error, flush=True)
                    else:
                        print("[Камера] " + answer, flush=True)
                        show_ai_answer(_ui.root, question, answer, None)
                elif ui_action == "inspect_camera_image":
                    _ui.set_busy_overlay("Получаю кадр и проверяю его через ИИ…")
                    threading.Thread(target=_camera_inspection_worker, daemon=True, name="camera-inspection").start()
                elif ui_action == "camera_inspection_result":
                    _ui.set_busy_overlay(None)
                    result_text, error = value
                    print("[Камера] " + (error if error else result_text), flush=True)
                elif ui_action == "open_assistant_settings":
                    from settings_window import open_settings_window
                    open_settings_window(_ui.root)
                elif ui_action == "open_reminders":
                    open_reminders(_ui.root)
                elif ui_action == "open_mail_client":
                    open_mail_client(_ui.root)
                elif ui_action == "confirm_read_mail":
                    from tkinter import messagebox
                    approved = messagebox.askyesno(
                        "Прочитать новые письма",
                        "Для составления сводки текст непрочитанных писем будет передан подключённой модели Ollama Cloud. Продолжить?",
                        parent=_ui.root,
                    )
                    if approved:
                        _ui.set_busy_overlay("Проверяю входящую почту…")
                        threading.Thread(target=_mail_reader_worker, daemon=True, name="mail-reader").start()
                    else:
                        _ui.set_busy_overlay(None)
                elif ui_action == "ai_chat":
                    question = str(value or "").strip()
                    if question:
                        print("[ИИ] Отправляю вопрос подключённой модели.", flush=True)
                        _ui.set_busy_overlay("Жду ответ ИИ…")
                        threading.Thread(target=_ask_ai_worker, args=(question,), daemon=True).start()
                elif ui_action == "ai_chat_result":
                    question, answer, error = value
                    _ui.set_busy_overlay(None)
                    show_ai_answer(_ui.root, question, answer, error)
                else:
                    print(f"[GUI] Неизвестное действие: {ui_action}", flush=True)
            except Exception:
                print(f"[GUI] Не удалось выполнить действие {ui_action}:", flush=True)
                traceback.print_exc()

        try:
            deliver_due_reminders()
        except Exception:
            print("[GUI] Ошибка доставки напоминаний:", flush=True)
            traceback.print_exc()

    _ui.root.after(25, process_background_events)
    _ui.run()


def shutdown():
    stop_reminder_service()
    with _lock:
        active = _recording
    if active:
        stop_recording()
    remove_keyboard_hook()
    print("Работа программы завершена.")

if __name__ == "__main__":
    main()
