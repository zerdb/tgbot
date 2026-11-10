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

_speech_queue: queue.Queue[str] = queue.Queue()
_speech_start_lock = threading.Lock()
_speech_worker_started = False


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


def _speech_worker():
    voice = None
    # Голос загружается лениво — только при первом напоминании или уведомлении.
    while True:
        text = _speech_queue.get()
        try:
            if voice is None:
                voice = _load_piper_voice()
            _speak_with_piper(voice, text)
        except Exception as exc:
            print(f"[Озвучивание] Ошибка Piper TTS: {exc}", flush=True)
        finally:
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
    _speech_queue.put(text)
