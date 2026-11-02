"""Push-to-talk voice typing with GigaAM.

Hold Right Ctrl to record. Release it to transcribe and paste the text.
Requires the official GigaAM package and ffmpeg.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd
import soundfile as sf
import gigaam


SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
CHANNELS = 1
MODEL_NAME = os.getenv("GIGAAM_MODEL", "v3_e2e_rnnt")
HOTKEY = os.getenv("PUSH_TO_TALK_KEY", "right ctrl")

_model = None
_stream = None
_audio_chunks: list[np.ndarray] = []
_recording = False
_lock = threading.Lock()
_transcription_lock = threading.Lock()


def load_model():
    global _model
    print(f"Loading GigaAM model: {MODEL_NAME} ...")
    _model = gigaam.load_model(MODEL_NAME)
    print("GigaAM is ready.")


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
        print("Transcribing...")
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
