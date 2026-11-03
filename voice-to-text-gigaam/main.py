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

from windows_actions import lock_computer, reboot_computer, open_downloads, open_settings, empty_recycle_bin, take_screenshot
from reminders import start_reminder_service, add_reminder
from email_manager import list_email_contacts
from email_form import open_email_form
from contact_form import open_contact_form
from file_search import search_web, search_files
from assistant_window import AssistantWindow

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
_ui = None


def update_ui_status(listening=None):
    if _ui is not None:
        _ui.set_status(listening=listening)


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
        update_ui_status("ИДЁТ ДИКТОВКА" if mode == "text" else "СЛУШАЮ ГОЛОСОВУЮ КОМАНДУ")
    except (sd.PortAudioError, OSError) as exc:
        with _lock:
            _recording = False
        _stream = None
        print(f"Не удалось начать запись: {exc}")
        update_ui_status("ОШИБКА ЗАПИСИ")


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
    update_ui_status("РАСПОЗНАЮ РЕЧЬ")
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
    command_text = normalize_command(text)
    print(f"Распознана голосовая команда: {text}")
    if command_text in {"добавить контакт", "добавь контакт", "создать контакт", "новый контакт"}:
        open_contact_form()
        return
    elif command_text in {"покажи контакты", "покажи адресную книгу", "список контактов"}:
        list_email_contacts()
        return
    elif command_text in {"отправь на почту", "отправить на почту", "отправь письмо", "открыть отправку почты"} or command_text.startswith(("отправь на почту ", "отправить на почту ")):
        subject = re.sub(r"^\s*отправ(?:ь|ить)\s+на\s+почту\s*", "", text, flags=re.IGNORECASE).strip(" .,!?:;«»")
        open_email_form(subject)
        return
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
        update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")


def main():
    global _ui
    progress("Проверяю микрофон...")
    microphone_found = check_microphone()
    progress("Настраиваю FFmpeg...")
    configure_ffmpeg()
    progress("Начинаю загрузку GigaAM...")
    load_model()
    start_reminder_service()
    progress("Голосовой ввод и голосовые команды готовы.")
    keyboard.on_press_key(TEXT_HOTKEY, lambda _: start_recording("text"), suppress=False)
    keyboard.on_release_key(TEXT_HOTKEY, lambda _: stop_recording(), suppress=False)
    keyboard.on_press_key(COMMAND_HOTKEY, lambda _: start_recording("command"), suppress=False)
    keyboard.on_release_key(COMMAND_HOTKEY, lambda _: stop_recording(), suppress=False)
    _ui = AssistantWindow(on_close=shutdown, microphone_status="НАЙДЕН" if microphone_found else "НЕ НАЙДЕН")
    _ui.run()


def shutdown():
    with _lock:
        active = _recording
    if active:
        stop_recording()
    keyboard.unhook_all()
    print("Работа программы завершена.")

if __name__ == "__main__":
    main()
