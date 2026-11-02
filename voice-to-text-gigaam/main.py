"""Offline push-to-talk voice typing using a locally stored GigaAM-v3 model.

Hold Right Ctrl to record. Release it to transcribe and paste the text.
The model is loaded only from disk; inference does not contact Hugging Face.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import traceback
from pathlib import Path

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
MODEL_DIR = Path(
    os.getenv("GIGAAM_MODEL_DIR", str(PROJECT_DIR.parent / "GigaAM-v3"))
).expanduser().resolve()

_model = None
_stream = None
_audio_chunks: list[np.ndarray] = []
_recording = False
_recording_mode = "text"
_lock = threading.Lock()
_transcription_lock = threading.Lock()


def configure_ffmpeg():
    """Создаёт ffmpeg.exe с ожидаемым Windows именем и добавляет его в PATH."""
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
            print("Подключите микрофон и перезапустите программу.")
            return False
    except (sd.PortAudioError, OSError) as exc:
        print(f"Микрофон не найден или недоступен: {exc}")
        print("Подключите микрофон и перезапустите программу.")
        return False

    print(f"Микрофон найден: {device['name']}")
    return True


def load_model():
    global _model

    if not (MODEL_DIR / "config.json").is_file():
        raise FileNotFoundError(
            f"Локальная модель GigaAM не найдена: {MODEL_DIR}\\n"
            "Скачайте ai-sage/GigaAM-v3 (revision e2e_rnnt) в папку "
            "'GigaAM-v3' рядом с папкой voice-to-text-gigaam "
            "или укажите путь к модели в переменной GIGAAM_MODEL_DIR."
        )

    progress(f"Загружаю локальную модель GigaAM из папки: {MODEL_DIR}")
    _model = AutoModel.from_pretrained(
        str(MODEL_DIR),
        trust_remote_code=True,
        local_files_only=True,
    )
    progress("Веса модели загружены. Перевожу модель в режим распознавания...")
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
        _stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=audio_callback,
        )
        _stream.start()
        key_name = "правый Shift" if mode == "text" else "правый Ctrl"
        purpose = "для ввода текста" if mode == "text" else "для голосовой команды"
        print(f"Идёт запись {purpose}. Отпустите {key_name}, чтобы выполнить.")
    except (sd.PortAudioError, OSError) as exc:
        with _lock:
            _recording = False
        _stream = None
        print(f"Не удалось начать запись: микрофон недоступен. {exc}")


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

    audio = np.concatenate(chunks, axis=0).reshape(-1)
    if audio.size == 0:
        print("Звук не записан.")
        return

    duration = len(audio) / SAMPLE_RATE
    print(f"Запись завершена: {duration:.2f} сек. Отправляю на распознавание...")
    worker = transcribe_and_paste if mode == "text" else transcribe_and_execute
    threading.Thread(target=worker, args=(audio,), daemon=True).start()


def transcribe_audio_file(audio: np.ndarray) -> str:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = Path(tmp.name)

        sf.write(str(temp_path), audio, SAMPLE_RATE, subtype="PCM_16")
        with torch.inference_mode():
            return _model.transcribe(str(temp_path)).strip()
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def transcribe_and_paste(audio: np.ndarray):
    if not _transcription_lock.acquire(blocking=False):
        print("Предыдущее распознавание ещё выполняется. Эта запись пропущена.")
        return

    try:
        print("Распознаю речь локально...")
        chunk_size = SAMPLE_RATE * MAX_CHUNK_SECONDS
        parts = [
            audio[start:start + chunk_size]
            for start in range(0, len(audio), chunk_size)
        ]

        recognized_parts = []
        for index, part in enumerate(parts, start=1):
            if len(parts) > 1:
                print(f"Распознаю фрагмент {index} из {len(parts)}...")
            result = transcribe_audio_file(part)
            if result:
                recognized_parts.append(result)

        text = " ".join(recognized_parts).strip()
        if text:
            pyperclip.copy(text)
            keyboard.send("ctrl+v")
            print(f"Текст распознан и вставлен: {text}")
        else:
            print("Речь не распознана.")
    except Exception as exc:
        print(f"Ошибка распознавания: {exc}")
        print("Подробности ошибки:")
        traceback.print_exc()
    finally:
        _transcription_lock.release()



def normalize_command(text: str) -> str:
    import re
    normalized = text.lower().replace("ё", "е")
    normalized = re.sub(r"[^а-яa-z0-9 ]+", " ", normalized)
    return " ".join(normalized.split())


def lock_computer():
    """Блокирует текущий сеанс Windows."""
    import ctypes
    if os.name != "nt":
        print("Команда блокировки поддерживается только в Windows.")
        return
    if not ctypes.windll.user32.LockWorkStation():
        raise OSError("Windows не смогла заблокировать рабочую станцию.")
    print("Компьютер заблокирован.")


# Реестр команд: новые команды добавляются отдельными записями.
COMMANDS = {
    "lock_computer": {
        "phrases": (
            "блокировка экрана",
            "блокировка компьютера",
            "заблокируй компьютер",
            "заблокируй комп",
            "заблокируй экран",
            "закблокируй компьютер",
            "закблокируй комп",
            "lock computer",
            "lock screen",
        ),
        "handler": lock_computer,
        "description": "Блокировка компьютера",
    },
}


def execute_voice_command(text: str):
    command_text = normalize_command(text)
    print(f"Распознана голосовая команда: {text}")
    for command in COMMANDS.values():
        phrases = {normalize_command(phrase) for phrase in command["phrases"]}
        if command_text in phrases:
            print(f"Выполняю команду: {command['description']}")
            command["handler"]()
            return
    print("Команда не найдена. Доступная команда: «заблокируй компьютер».")


def transcribe_and_execute(audio: np.ndarray):
    if not _transcription_lock.acquire(blocking=False):
        print("Предыдущее распознавание ещё выполняется. Эта запись пропущена.")
        return
    try:
        print("Распознаю голосовую команду...")
        chunk_size = SAMPLE_RATE * MAX_CHUNK_SECONDS
        parts = [audio[start:start + chunk_size] for start in range(0, len(audio), chunk_size)]
        recognized_parts = []
        for index, part in enumerate(parts, start=1):
            if len(parts) > 1:
                print(f"Распознаю фрагмент команды {index} из {len(parts)}...")
            result = transcribe_audio_file(part)
            if result:
                recognized_parts.append(result)
        text = " ".join(recognized_parts).strip()
        if text:
            execute_voice_command(text)
        else:
            print("Голосовая команда не распознана.")
    except Exception as exc:
        print(f"Ошибка выполнения голосовой команды: {exc}")
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
    progress("Голосовой ввод и голосовые команды готовы.")
    print("Правый Shift — диктовка текста; правый Ctrl — голосовые команды.")
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
