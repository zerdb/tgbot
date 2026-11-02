"""Offline push-to-talk voice typing using a locally stored GigaAM-v3 model.

Expected layout:
    tgbot/
      GigaAM-v3/                 # downloaded Hugging Face model snapshot
      voice-to-text-gigaam/
        main.py

Hold Right Ctrl to record. Release it to transcribe and paste the text.
The model is loaded only from disk; inference does not contact Hugging Face.
"""
from __future__ import annotations

import os
import tempfile
import threading
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


def load_model():
    global _model

    if not (MODEL_DIR / "config.json").is_file():
        raise FileNotFoundError(
            f"Local GigaAM model not found: {MODEL_DIR}\n"
            "Download ai-sage/GigaAM-v3 (revision e2e_rnnt) into a folder "
            "named 'GigaAM-v3' next to the voice-to-text-gigaam project, "
            "or set GIGAAM_MODEL_DIR to the model folder."
        )

    print(f"Loading local GigaAM model from: {MODEL_DIR}")
    # trust_remote_code is required by the official GigaAM model architecture.
    # local_files_only prevents any network access or automatic model download.
    _model = AutoModel.from_pretrained(
        str(MODEL_DIR),
        trust_remote_code=True,
        local_files_only=True,
    )
    _model.eval()
    print("GigaAM is ready (offline mode).")


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Audio status: {status}")
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
        print("Recording... release Right Ctrl to transcribe.")
    except Exception:
        with _lock:
            _recording = False
        raise


def stop_recording():
    global _stream, _recording
    with _lock:
        if not _recording:
            return
        _recording = False
        chunks = list(_audio_chunks)

    stream, _stream = _stream, None
    if stream is not None:
        stream.stop()
        stream.close()

    if not chunks:
        print("No audio captured.")
        return

    audio = np.concatenate(chunks, axis=0).reshape(-1)
    if len(audio) < SAMPLE_RATE // 4:
        print("Recording is too short; skipped.")
        return
    if len(audio) > SAMPLE_RATE * 25:
        print("Recording exceeds GigaAM short-audio limit (25 seconds); skipped.")
        return

    threading.Thread(target=transcribe_and_paste, args=(audio,), daemon=True).start()


def transcribe_and_paste(audio: np.ndarray):
    if not _transcription_lock.acquire(blocking=False):
        print("Previous transcription is still running; skipped.")
        return

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = Path(tmp.name)

        sf.write(str(temp_path), audio, SAMPLE_RATE, subtype="PCM_16")
        print("Transcribing locally...")
        with torch.inference_mode():
            text = _model.transcribe(str(temp_path)).strip()

        if text:
            pyperclip.copy(text)
            keyboard.send("ctrl+v")
            print(f"Pasted: {text}")
        else:
            print("No speech recognized.")
    except Exception as exc:
        print(f"Transcription error: {exc}")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        _transcription_lock.release()


def main():
    load_model()
    print(f"Push-to-talk is active. Hold {HOTKEY} to speak.")
    print("Press Esc to quit.")

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
        print("Stopped.")


if __name__ == "__main__":
    main()
