"""Windows toast notifications and local Piper neural speech synthesis."""
from __future__ import annotations

import hashlib
import json
import importlib
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import requests
from winotify import Notification, audio


def show_notification(title: str, message: str):
    """Show a Windows notification and announce it with the local voice."""
    toast = Notification(app_id="Zero Control", title=title, msg=message, duration="long")
    toast.set_audio(audio.Default, loop=False)
    toast.show()
    speak_text(". ".join(part.strip() for part in (title, message) if part and part.strip()))


# Russian medium-quality male voice. The model is downloaded once and then used offline.
_PIPER_VOICE_ID = "ru_RU-denis-medium"
_PIPER_MODEL_DIR = Path(__file__).resolve().parent / "models" / "piper"
_PIPER_MODEL_NAME = f"{_PIPER_VOICE_ID}.onnx"
_PIPER_MODEL_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "ru/ru_RU/denis/medium/"
)
_PIPER_MODEL_SHA256 = "15fab56e11a097858ee115545d0f697fc2a316c41a291a5362349fb870411b0a"

_speech_queue: queue.Queue[tuple[str, str]] = queue.Queue()
_speech_start_lock = threading.Lock()
_speech_worker_started = False
_speech_control_lock = threading.RLock()
_active_clipboard_session = None
_speech_state_callback = None


class _ClipboardSpeechSession:
    def __init__(self):
        self.paused = False
        self.stopped = False
        self.speed = 1.0


def set_speech_state_callback(callback):
    """Register a UI callback receiving (status, speed) for clipboard reading."""
    global _speech_state_callback
    with _speech_control_lock:
        _speech_state_callback = callback


def _notify_speech_state(status):
    with _speech_control_lock:
        callback = _speech_state_callback
        session = _active_clipboard_session
        speed = session.speed if session is not None else 1.0
    if callback is not None:
        try:
            callback(status, speed)
        except Exception as exc:
            print(f"[Озвучивание] Не удалось обновить панель управления: {exc}", flush=True)


def is_clipboard_reading_active():
    with _speech_control_lock:
        return _active_clipboard_session is not None


def _change_clipboard_session(action):
    with _speech_control_lock:
        session = _active_clipboard_session
        if session is None:
            return False
        if action == "pause":
            session.paused = True
        elif action == "resume":
            session.paused = False
        elif action == "stop":
            session.stopped = True
            session.paused = False
        elif action == "faster":
            session.speed = min(1.6, round(session.speed + 0.1, 1))
        elif action == "slower":
            session.speed = max(0.7, round(session.speed - 0.1, 1))
        speed = session.speed
        status = "paused" if session.paused else "playing"
    if action == "stop":
        _notify_speech_state("stopping")
    else:
        _notify_speech_state(status)
    return True


def pause_clipboard_reading():
    return _change_clipboard_session("pause")


def resume_clipboard_reading():
    return _change_clipboard_session("resume")


def stop_clipboard_reading():
    return _change_clipboard_session("stop")


def increase_clipboard_reading_speed():
    return _change_clipboard_session("faster")


def decrease_clipboard_reading_speed():
    return _change_clipboard_session("slower")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_piper_voice_file(filename: str, expected_sha256: str | None = None) -> Path:
    destination = _PIPER_MODEL_DIR / filename
    if destination.is_file():
        if filename.endswith(".json"):
            try:
                with destination.open("r", encoding="utf-8") as source:
                    config = json.load(source)
                if config.get("audio", {}).get("sample_rate") and config.get("phoneme_id_map"):
                    return destination
            except (OSError, ValueError):
                pass
        elif expected_sha256 and _file_sha256(destination) == expected_sha256:
            return destination

    _PIPER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    url = _PIPER_MODEL_URL + filename + "?download=true"
    temporary_path = None
    print(f"[Озвучивание] Загружаю голосовую модель: {filename}", flush=True)
    try:
        with requests.get(url, stream=True, timeout=(20, 120)) as response:
            response.raise_for_status()
            digest = hashlib.sha256()
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=_PIPER_MODEL_DIR, suffix=".part", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        temporary.write(chunk)
                        digest.update(chunk)
        if expected_sha256 and digest.hexdigest() != expected_sha256:
            raise RuntimeError(f"SHA-256 файла {filename} не совпала.")
        if filename.endswith(".json"):
            with temporary_path.open("r", encoding="utf-8") as source:
                config = json.load(source)
            if not config.get("audio", {}).get("sample_rate") or not config.get("phoneme_id_map"):
                raise RuntimeError(f"Файл конфигурации голоса {filename} повреждён.")
        os.replace(temporary_path, destination)
        temporary_path = None
        print(f"[Озвучивание] Файл готов: {filename}", flush=True)
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _ensure_piper_installed():
    try:
        return importlib.import_module("piper")
    except ImportError:
        print("[Озвучивание] Устанавливаю локальный движок Piper TTS…", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "piper-tts>=1.3.0,<2.0.0"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "pip завершился без описания ошибки").strip()
            raise RuntimeError(f"Не удалось установить Piper TTS: {details[-2500:]}")
        importlib.invalidate_caches()
        return importlib.import_module("piper")


def _load_piper_voice():
    piper = _ensure_piper_installed()
    model_path = _download_piper_voice_file(_PIPER_MODEL_NAME, _PIPER_MODEL_SHA256)
    _download_piper_voice_file(_PIPER_MODEL_NAME + ".json")
    print("[Озвучивание] Загружаю русский голос Denis в память…", flush=True)
    voice = piper.PiperVoice.load(str(model_path))
    print("[Озвучивание] Локальный голос Denis готов.", flush=True)
    return voice


def _speak_with_piper(voice, text: str):
    import winsound

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temporary:
        wav_path = Path(temporary.name)
    try:
        with wave.open(str(wav_path), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
    finally:
        wav_path.unlink(missing_ok=True)


def _play_clipboard_audio(wav_path: Path, session):
    """Play clipboard speech with interruptible pause/stop and live speed control."""
    import numpy as np
    import sounddevice as sd

    with wave.open(str(wav_path), "rb") as source:
        channels = source.getnchannels()
        sample_rate = source.getframerate()
        sample_width = source.getsampwidth()
        if sample_width != 2:
            raise RuntimeError("Piper вернул WAV в неподдерживаемом формате.")
        audio_data = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    if channels > 1:
        audio_data = audio_data.reshape(-1, channels)
    else:
        audio_data = audio_data.reshape(-1, 1)
    audio_data = audio_data.astype(np.float32) / 32768.0
    position = 0.0

    def callback(outdata, frames, _time_info, _status):
        nonlocal position
        with _speech_control_lock:
            stopped = session.stopped
            paused = session.paused
            speed = session.speed
        if stopped:
            outdata.fill(0)
            raise sd.CallbackStop
        if paused:
            outdata.fill(0)
            return
        positions = position + np.arange(frames, dtype=np.float64) * speed
        valid = positions < len(audio_data)
        if not np.any(valid):
            outdata.fill(0)
            raise sd.CallbackStop
        lower = positions.astype(np.int64)
        upper = np.minimum(lower + 1, len(audio_data) - 1)
        fraction = (positions - lower).astype(np.float32)
        for channel in range(channels):
            samples = audio_data[:, channel]
            outdata[:, channel] = (
                samples[lower] * (1.0 - fraction) + samples[upper] * fraction
            )
        outdata[~valid] = 0
        position += frames * speed
        if position >= len(audio_data):
            raise sd.CallbackStop

    with sd.OutputStream(
        samplerate=sample_rate, channels=channels, dtype="float32",
        callback=callback,
    ):
        while True:
            with _speech_control_lock:
                stopped = session.stopped
            if stopped:
                break
            time.sleep(0.05)


def _speak_clipboard_with_piper(voice, text, session):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temporary:
        wav_path = Path(temporary.name)
    try:
        with wave.open(str(wav_path), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        with _speech_control_lock:
            stopped = session.stopped
        if not stopped:
            _play_clipboard_audio(wav_path, session)
    finally:
        wav_path.unlink(missing_ok=True)


def _speech_worker():
    global _active_clipboard_session
    voice = None
    while True:
        item_type, text = _speech_queue.get()
        session = None
        try:
            if item_type == "clipboard":
                session = _ClipboardSpeechSession()
                with _speech_control_lock:
                    _active_clipboard_session = session
                _notify_speech_state("preparing")
            if voice is None:
                voice = _load_piper_voice()
            if item_type == "clipboard":
                with _speech_control_lock:
                    stopped = session.stopped
                if not stopped:
                    _speak_clipboard_with_piper(voice, text, session)
            else:
                _speak_with_piper(voice, text)
        except Exception as exc:
            print(f"[Озвучивание] Ошибка Piper TTS: {exc}", flush=True)
        finally:
            if session is not None:
                with _speech_control_lock:
                    if _active_clipboard_session is session:
                        _active_clipboard_session = None
                _notify_speech_state("finished")
            _speech_queue.task_done()


def initialize_speech_engine():
    """Start loading Piper in the background during application startup."""
    global _speech_worker_started
    with _speech_start_lock:
        if _speech_worker_started:
            return
        worker = threading.Thread(
            target=_speech_worker,
            name="zero-control-piper-tts",
            daemon=True,
        )
        worker.start()
        _speech_worker_started = True


def speak_text(message: str):
    """Queue text for asynchronous local Russian neural speech synthesis."""
    text = str(message or "").strip()
    if not text:
        return
    initialize_speech_engine()
    _speech_queue.put(("notification", text))


def speak_clipboard_text(message: str):
    """Queue clipboard text in a separately controllable local speech session."""
    text = str(message or "").strip()
    if not text:
        return
    initialize_speech_engine()
    _speech_queue.put(("clipboard", text))
