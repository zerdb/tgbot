"""Offline push-to-talk voice typing and Windows voice commands for GigaAM-v3."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

from file_indexer import refresh_and_search

_STARTUP_TIME = time.perf_counter()


def progress(message: str):
    elapsed = time.perf_counter() - _STARTUP_TIME
    print(f"[{elapsed:6.1f} сек] {message}", flush=True)


progress("Запуск Python: загружаю аудиобиблиотеки...")
import imageio_ffmpeg
import keyboard
import numpy as np
import pyperclip
import sounddevice as sd
import soundfile as sf
from PIL import ImageGrab
from winotify import Notification, audio
progress("Аудиобиблиотеки загружены. Загружаю PyTorch...")
import torch
progress("PyTorch загружен. Загружаю Transformers...")
from transformers import AutoModel
progress("Библиотеки загружены.")

SAMPLE_RATE = 16000
CHANNELS = 1
TEXT_HOTKEY = "right shift"
COMMAND_HOTKEY = "right ctrl"
MAX_CHUNK_SECONDS = 24

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
_reminder_lock = threading.Lock()
_reminders: list[tuple[datetime, str]] = []
_reminder_thread_started = False


def configure_ffmpeg():
    source = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    target_dir = Path(tempfile.gettempdir()) / "gigaam_ffmpeg"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "ffmpeg.exe"
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        shutil.copy2(source, target)
    os.environ["PATH"] = str(target_dir) + os.pathsep + os.environ.get("PATH", "")
    progress(f"FFmpeg настроен: {target}")


def check_microphone() -> bool:
    try:
        device = sd.query_devices(kind="input")
        if device["max_input_channels"] < CHANNELS:
            print("Микрофон не найден: устройство не поддерживает запись звука.")
            return False
    except (sd.PortAudioError, OSError) as exc:
        print(f"Микрофон не найден или недоступен: {exc}")
        return False
    print(f"Микрофон найден: {device['name']}")
    return True


def load_model():
    global _model
    if not (MODEL_DIR / "config.json").is_file():
        raise FileNotFoundError(
            f"Локальная модель GigaAM не найдена: {MODEL_DIR}\n"
            "Поместите модель ai-sage/GigaAM-v3 (revision e2e_rnnt) "
            "в папку GigaAM-v3 рядом с voice-to-text-gigaam."
        )
    progress(f"Загружаю локальную модель GigaAM: {MODEL_DIR}")
    _model = AutoModel.from_pretrained(str(MODEL_DIR), trust_remote_code=True, local_files_only=True)
    _model.eval()
    progress("Модель GigaAM готова к работе (автономный режим).")


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
        _stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", callback=audio_callback)
        _stream.start()
        key_name = "правый Shift" if mode == "text" else "правый Ctrl"
        purpose = "для ввода текста" if mode == "text" else "для голосовой команды"
        print(f"Идёт запись {purpose}. Отпустите {key_name}, чтобы выполнить.")
    except (sd.PortAudioError, OSError) as exc:
        with _lock:
            _recording = False
        _stream = None
        print(f"Не удалось начать запись: {exc}")


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
    if not chunks:
        print("Звук не записан: микрофон не передал аудиоданные.")
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


def normalize_command(text: str) -> str:
    normalized = text.lower().replace("ё", "е")
    normalized = re.sub(r"[^а-яa-z0-9.:/ -]+", " ", normalized)
    # ASR often adds a final period or comma; it must not break exact commands.
    return " ".join(normalized.split()).strip(" .,:;!?")


def windows_only():
    if os.name != "nt":
        raise OSError("Эта команда поддерживается только в Windows.")


def confirm_action(title: str, message: str) -> bool:
    windows_only()
    import ctypes
    return ctypes.windll.user32.MessageBoxW(None, message, title, 0x4 | 0x20) == 6




def lock_computer():
    windows_only()
    import ctypes
    if not ctypes.windll.user32.LockWorkStation():
        raise OSError("Windows не смогла заблокировать рабочую станцию.")
    print("Компьютер заблокирован.")


def reboot_computer():
    if not confirm_action("Подтверждение перезагрузки", "Перезагрузить компьютер сейчас? Сохраните открытые документы."):
        print("Перезагрузка отменена.")
        return
    subprocess.Popen(["shutdown", "/r", "/t", "0"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _bring_window_to_front(title_parts: tuple[str, ...], timeout: float = 3.0):
    """Restore and foreground an already-open Windows window by its title."""
    import ctypes
    import time

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    target = None
    deadline = time.monotonic() + timeout

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_callback(hwnd, _):
        nonlocal target
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.casefold()
        if any(part.casefold() in title for part in title_parts):
            target = hwnd
            return False
        return True

    while time.monotonic() < deadline:
        target = None
        user32.EnumWindows(enum_callback, 0)
        if target:
            SW_RESTORE = 9
            user32.ShowWindow(target, SW_RESTORE)
            user32.BringWindowToTop(target)
            # Windows may deny foreground activation to a background process.
            # Attach input queues briefly so the existing window gets focus.
            foreground = user32.GetForegroundWindow()
            current_thread = kernel32.GetCurrentThreadId()
            target_thread = user32.GetWindowThreadProcessId(target, None)
            foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
            attached_target = False
            attached_foreground = False
            try:
                if target_thread and target_thread != current_thread:
                    attached_target = bool(user32.AttachThreadInput(current_thread, target_thread, True))
                if foreground_thread and foreground_thread != current_thread:
                    attached_foreground = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))
                user32.SetForegroundWindow(target)
                user32.SetActiveWindow(target)
                user32.SetFocus(target)
            finally:
                if attached_foreground:
                    user32.AttachThreadInput(current_thread, foreground_thread, False)
                if attached_target:
                    user32.AttachThreadInput(current_thread, target_thread, False)
            return
        time.sleep(0.15)


def open_downloads():
    windows_only()
    path = Path.home() / "Downloads"
    if not path.exists():
        path = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Загрузки"
    os.startfile(str(path))
    _bring_window_to_front(("Загрузки", "Downloads"))


def open_settings():
    windows_only()
    os.startfile("ms-settings:")
    _bring_window_to_front(("Параметры", "Settings"))


def empty_recycle_bin():
    if not confirm_action("Очистка корзины", "Безвозвратно удалить все файлы из корзины? Это действие нельзя отменить."):
        print("Очистка корзины отменена.")
        return
    import ctypes
    result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4)
    if result:
        raise OSError(f"Не удалось очистить корзину (код {result}).")
    print("Корзина очищена.")


def take_screenshot():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    destination = SCREENSHOT_DIR / f"Screenshot_{stamp}.png"
    counter = 1
    while destination.exists():
        destination = SCREENSHOT_DIR / f"Screenshot_{stamp}_{counter}.png"
        counter += 1
    ImageGrab.grab(all_screens=True).save(destination, "PNG")
    print(f"Скриншот сохранён: {destination}")
    try:
        os.startfile(str(destination))
        print("Открываю скриншот.")
    except OSError as exc:
        print(f"Скриншот сохранён, но не удалось открыть его автоматически: {exc}")


def show_notification(title: str, message: str):
    toast = Notification(app_id="GigaAM Voice Assistant", title=title, msg=message, duration="long")
    toast.set_audio(audio.Default, loop=False)
    toast.show()


def speak_text(message: str):
    # Windows встроенный SAPI, не требует отдельного TTS-пакета или интернета.
    escaped = message.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak('{escaped}')"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-Command", script],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def reminder_worker():
    while True:
        due = []
        now = datetime.now()
        with _reminder_lock:
            remaining = []
            for when, message in _reminders:
                if when <= now:
                    due.append((when, message))
                else:
                    remaining.append((when, message))
            _reminders[:] = remaining
        for when, message in due:
            print(f"НАПОМИНАНИЕ: {message}")
            try:
                show_notification("Напоминание", message)
            except Exception as exc:
                print(f"Не удалось показать уведомление: {exc}")
            speak_text("Напоминание. " + message)
        time.sleep(1)


def start_reminder_service():
    global _reminder_thread_started
    if not _reminder_thread_started:
        threading.Thread(target=reminder_worker, daemon=True, name="reminder-service").start()
        _reminder_thread_started = True


def parse_reminder(text: str):
    source = normalize_command(text)
    if not source.startswith("напомни "):
        return None
    body = source[len("напомни "):].strip()
    # В разговорной речи часто говорят «напомни мне ...».
    body = re.sub(r"^мне\\s+", "", body)
    now = datetime.now()
    due = None
    rest = body

    # Относительное время: «через минуту», «через час», «через 1 час 20 минут».
    if rest.startswith("через "):
        m = re.match(r"через\\s+полчаса(?:\\s+|$)(.*)", rest)
        if m:
            due, rest = now + timedelta(minutes=30), m.group(1).strip()
        else:
            m = re.match(
                r"через\\s+"
                r"(?:(\\d+)\\s*(?:час|часа|часов|ч)\\s*)?"
                r"(?:(\\d+)\\s*(?:минуту|минуты|минут|минута|мин)\\s*)?"
                r"(?:(\\d+)\\s*(?:секунду|секунды|секунд|сек)\\s*)?"
                r"(.*)",
                rest,
            )
            if m:
                hours, minutes, seconds = (int(m.group(i) or 0) for i in (1, 2, 3))
                remainder = m.group(4).strip()
                # Если единица времени названа без числа, подразумевается одна.
                if not any(m.group(i) for i in (1, 2, 3)):
                    unit = re.match(r"через\\s+(час|часа|часов|ч|минуту|минута|минуты|минут|мин|секунду|секунда|секунды|секунд|сек)\\b", rest)
                    if unit:
                        token = unit.group(1)
                        if token in {"час", "часа", "часов", "ч"}:
                            hours = 1
                        elif token in {"минуту", "минута", "минуты", "минут", "мин"}:
                            minutes = 1
                        else:
                            seconds = 1
                        remainder = rest[unit.end():].strip()
                if hours or minutes or seconds:
                    due = now + timedelta(hours=hours, minutes=minutes, seconds=seconds)
                    rest = remainder
    # "завтра в 9 утра", "завтра утром", "завтра в 09:30".
    if due is None and rest.startswith("завтра"):
        tomorrow = now.date() + timedelta(days=1)
        m = re.match(r"завтра\s+в\s+(\d{1,2})(?::(\d{2}))?\s*(утра|вечера|дня)?\s*(.*)", rest)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            period = m.group(3)
            if period == "вечера" and hour < 12:
                hour += 12
            elif period in ("утра", "дня") and hour == 12:
                hour = 0 if period == "утра" else 12
            if hour > 23 or minute > 59:
                return None
            due = datetime.combine(tomorrow, datetime.min.time()).replace(hour=hour, minute=minute)
            rest = m.group(4).strip()
        else:
            m = re.match(r"завтра\s+(утром|днем|днём|вечером|ночью)\s*(.*)", rest)
            if m:
                hour = {"утром": 9, "днем": 13, "днём": 13, "вечером": 18, "ночью": 22}[m.group(1)]
                due = datetime.combine(tomorrow, datetime.min.time()).replace(hour=hour)
                rest = m.group(2).strip()
    if due is None or due <= now or not rest:
        return None
    return due, rest


def add_reminder(text: str):
    parsed = parse_reminder(text)
    if not parsed:
        print("Не удалось разобрать напоминание. Примеры: «напомни через полчаса проверить почту», "
              "«напомни через 1 час 20 минут позвонить», «напомни завтра в 9 утра о встрече».")
        return
    due, message = parsed
    with _reminder_lock:
        _reminders.append((due, message))
    print(f"Напоминание установлено на {due:%d.%m.%Y %H:%M}: {message}")


def search_web(text: str):
    query = re.sub(r"^\s*найди\s+в\s+интернете\s*", "", text, flags=re.IGNORECASE).strip()
    if not query:
        print("Не распознан поисковый запрос.")
        return
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
    print(f"Открываю поиск в интернете: {query}")


def show_file_results(paths: list[Path], query: str):
    import tkinter as tk
    from tkinter import ttk, messagebox
    root = tk.Tk()
    root.title(f"Результаты поиска: {query}")
    root.geometry("850x420")
    root.minsize(550, 260)
    # Окно создаётся после фонового поиска: явно выводим его на передний план,
    # иначе Windows может оставить его позади главного окна/терминала.
    root.attributes("-topmost", True)
    root.update_idletasks()
    root.deiconify()
    root.lift()
    root.focus_force()
    root.after(700, lambda: root.attributes("-topmost", False))
    ttk.Label(root, text=f"Найдено файлов: {len(paths)}. Двойной щелчок — открыть файл.").pack(
        anchor="w", padx=12, pady=(12, 6))
    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True, padx=12, pady=6)
    scrollbar = ttk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")
    listing = tk.Listbox(frame, yscrollcommand=scrollbar.set, font=("Segoe UI", 10))
    listing.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=listing.yview)
    for path in paths:
        listing.insert("end", str(path))
    def open_selected(_event=None):
        selection = listing.curselection()
        if selection:
            try:
                os.startfile(str(paths[selection[0]]))
            except OSError as exc:
                messagebox.showerror("Не удалось открыть файл", str(exc))
    listing.bind("<Double-Button-1>", open_selected)
    ttk.Button(root, text="Открыть выбранный файл", command=open_selected).pack(pady=(0, 12))
    root.mainloop()


def search_files(text: str):
    # Поддерживаем обе формулировки: «найди файл ...» и «найди ...».
    query = re.sub(r"^\s*найди\s+(?:файл\s+)?", "", text, flags=re.IGNORECASE).strip().strip('"«»')
    # Убираем знаки препинания, которые распознавание речи часто добавляет в конце фразы.
    # Убираем финальную пунктуацию распознавания, включая несколько знаков подряд.
    query = query.rstrip(" \t\r\n.,!?;:…。،؛؟\"'»”’)]}")
    query = query.strip()
    if not query:
        print("Не распознано имя файла. Скажите, например: «найди файл договор».")
        return
    threading.Thread(target=run_file_search, args=(query,), daemon=True, name="file-search").start()


def run_file_search(query: str):
    print(f"Ищу «{query}» по MFT и SQLite. Первое индексирование может занять некоторое время...")
    try:
        matches = refresh_and_search(
            query,
            report=lambda message: print(f"[Поиск файлов] {message}", flush=True),
        )
    except Exception as exc:
        print(f"Ошибка MFT-поиска: {exc}")
        try:
            show_notification("Поиск файлов", str(exc))
        except Exception:
            pass
        return

    if not matches:
        print(f"Файлы по запросу «{query}» не найдены.")
        try:
            show_notification("Поиск файлов", f"Файлы «{query}» не найдены.")
        except Exception:
            pass
        return

    print(f"Найдено файлов: {len(matches)}")
    try:
        show_file_results(matches, query)
    except Exception as exc:
        print(f"Не удалось открыть окно результатов: {exc}")
        traceback.print_exc()


def handle_command(text: str):
    command_text = normalize_command(text)
    print(f"Распознана голосовая команда: {text}")
    if command_text in {"блокировка экрана", "блокировка компьютера", "заблокируй компьютер",
                        "заблокируй комп", "заблокируй экран", "заблокируй пк",
                        "блокируй компьютер", "блокируй комп", "закблокируй компьютер",
                        "закблокируй комп", "заблокировать компьютер", "заблокировать комп",
                        "lock computer", "lock screen"}:
        lock_computer()
    elif command_text in {"перезагрузи компьютер", "перезагрузи комп", "перезагрузка компьютера"}:
        reboot_computer()
    elif command_text in {"покажи загрузки", "открой загрузки", "открой папку загрузки"}:
        open_downloads()
    elif command_text in {"открой настройки", "открой настройки windows"}:
        open_settings()
    elif command_text in {"очисти корзину", "очистить корзину"}:
        empty_recycle_bin()
    elif command_text in {"сделай скриншот", "сделай снимок экрана", "скриншот"}:
        take_screenshot()
    elif command_text.startswith("напомни "):
        add_reminder(text)
    elif command_text.startswith("найди в интернете "):
        search_web(text)
    elif command_text.startswith("найди файл ") or command_text.startswith("найди "):
        search_files(text)
    else:
        print("Команда не распознана. Проверьте формулировку и попробуйте ещё раз.")


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


def main():
    progress("Проверяю микрофон...")
    if not check_microphone():
        return
    progress("Настраиваю FFmpeg...")
    configure_ffmpeg()
    progress("Начинаю загрузку GigaAM...")
    load_model()
    start_reminder_service()
    progress("Голосовой ввод и голосовые команды готовы.")
    print("Правый Shift — диктовка текста; правый Ctrl — голосовые команды.")
    print("Команды: заблокируй компьютер; перезагрузи компьютер; покажи загрузки; "
          "открой настройки; очисти корзину; сделай скриншот; напомни ...; "
          "найди в интернете ...; найди файл ...")
    print("Для выхода нажмите Esc.")
    keyboard.on_press_key(TEXT_HOTKEY, lambda _: start_recording("text"), suppress=False)
    keyboard.on_release_key(TEXT_HOTKEY, lambda _: stop_recording(), suppress=False)
    keyboard.on_press_key(COMMAND_HOTKEY, lambda _: start_recording("command"), suppress=False)
    keyboard.on_release_key(COMMAND_HOTKEY, lambda _: stop_recording(), suppress=False)
    try:
        keyboard.wait("esc")
    except KeyboardInterrupt:
        pass
    finally:
        with _lock:
            active = _recording
        if active:
            stop_recording()
        keyboard.unhook_all()
        print("Работа программы завершена.")


if __name__ == "__main__":
    main()
