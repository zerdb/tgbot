"""Offline push-to-talk voice typing using a locally stored GigaAM-v3 model.

Hold Right Ctrl to record. Release it to transcribe and paste the text.
The model is loaded only from disk; inference does not contact Hugging Face.
"""
from __future__ import annotations

import os
import tempfile
import threading
import traceback
from pathlib import Path

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd
import soundfile as sf
import torch
from transformers import AutoModel


SAMPLE_RATE = 16000
CHANNELS = 1
HOTKEY = os.getenv("PUSH_TO_TALK_KEY", "right ctrl")
# GigaAM .transcribe() принимает аудио до 25 секунд.
MAX_CHUNK_SECONDS = 24

PROJECT_DIR = Path(__file__).resolve().parent
MODEL_DIR = Path(
    os.getenv("GIGAAM_MODEL_DIR", str(PROJECT_DIR.parent / "GigaAM-v3"))
).expanduser().resolve()

_model = None
_stream = None
_audio_chunks: list[np.ndarray] = []
_recording = False
_lock = threading.Lock()
_transcription_lock = threading.Lock()


def check_microphone() -> bool:
    """Проверяет наличие доступного устройства записи."""
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
            f"Локальная модель GigaAM не найдена: {MODEL_DIR}\n"
            "Скачайте ai-sage/GigaAM-v3 (revision e2e_rnnt) в папку "
            "'GigaAM-v3' рядом с папкой voice-to-text-gigaam "
            "или укажите путь к модели в переменной GIGAAM_MODEL_DIR."
        )

    print(f"Загружаю локальную модель GigaAM из папки: {MODEL_DIR}")
    _model = AutoModel.from_pretrained(
        str(MODEL_DIR),
        trust_remote_code=True,
        local_files_only=True,
    )
    _model.eval()
    print("Модель GigaAM готова к работе (автономный режим).")


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Состояние аудиоустройства: {status}")
    with _lock:
        if _recording:
            _audio_chunks.append(indata.copy())


def start_recording():
    global _stream, _recording, _audio_chunks

    with _lock:
        if _recording:
            return
        _audio_chunks = []
        _recording = True

    try:
        _stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=audio_callback,
        )
        _stream.start()
        print("Идёт запись... Отпустите правый Ctrl, чтобы распознать речь.")
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
    threading.Thread(target=transcribe_and_paste, args=(audio,), daemon=True).start()


def transcribe_audio_file(audio: np.ndarray) -> str:
    """Сохраняет фрагмент во временный WAV и распознаёт его."""
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


def main():
    if not check_microphone():
        return

    load_model()
    print(f"Голосовой ввод включён. Удерживайте {HOTKEY} и говорите.")
    print("Для выхода нажмите Esc.")

    keyboard.on_press_key(HOTKEY, lambda _: start_recording(), suppress=False)
    keyboard.on_release_key(HOTKEY, lambda _: stop_recording(), suppress=False)

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
