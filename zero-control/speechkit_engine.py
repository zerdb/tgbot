"""Yandex SpeechKit Recognition API v3 streaming client."""
from __future__ import annotations

import os
from typing import Any, Callable, Iterable

API_FOLDER_ID = "b1gfpt3ceq4e2au6p5md"
AUDIO_CHUNK_BYTES = 12800  # около 400 мс: 16 kHz, mono, PCM16
REQUEST_TIMEOUT_SECONDS = 90


def _create_stt():
    api_key = os.getenv("YC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Не найден YC_API_KEY. Добавьте ключ Yandex Cloud в переменные "
            "окружения Windows и перезапустите Zero Control."
        )
    from yandex_ai_studio_sdk import AIStudio

    folder_id = os.getenv("YC_FOLDER_ID", "").strip() or API_FOLDER_ID
    sdk = AIStudio(auth=api_key, folder_id=folder_id)
    return sdk.speechkit.speech_to_text(
        model="general",
        audio_format=sdk.speechkit.AudioFormat.PCM16(16000),
        language_codes="ru-RU",
        text_normalization=True,
    )


def _events_to_text(events: Iterable[Any], on_partial: Callable[[str], None] | None = None) -> str:
    final_texts = []
    refined_texts = []
    latest_partial = ""
    for event in events:
        if event.event_type == "partial":
            partial = (event.partial_text or "").strip()
            if partial and partial != latest_partial:
                latest_partial = partial
                print(f"[SpeechKit v3] {partial}", flush=True)
                if on_partial is not None:
                    on_partial(partial)
        elif event.event_type == "final":
            value = (event.final_text or "").strip()
            if value:
                final_texts.append(value)
                latest_partial = ""
                if on_partial is not None:
                    on_partial(" ".join(final_texts))
        elif event.event_type == "final_refinement":
            value = (event.final_refinement_text or "").strip()
            if value:
                refined_texts.append(value)

    result = refined_texts or final_texts
    return " ".join(part.strip() for part in result if part.strip()).strip()


def transcribe_audio_stream(
    audio_queue,
    stop_token,
    numpy_module=None,
    on_partial: Callable[[str], None] | None = None,
) -> str:
    """Read microphone blocks from a queue and upload them while recording.

    The producer puts mono float32 numpy arrays into audio_queue and puts
    stop_token after the microphone stream has been closed.
    """
    if numpy_module is None:
        import numpy as numpy_module

    stt = _create_stt()

    def pcm_chunks():
        pending = bytearray()
        while True:
            block = audio_queue.get()
            if block is stop_token:
                break
            audio = numpy_module.asarray(block, dtype=numpy_module.float32).reshape(-1)
            if audio.size:
                pcm = (
                    numpy_module.clip(audio, -1.0, 1.0) * 32767.0
                ).astype("<i2", copy=False).tobytes()
                pending.extend(pcm)
                while len(pending) >= AUDIO_CHUNK_BYTES:
                    yield bytes(pending[:AUDIO_CHUNK_BYTES])
                    del pending[:AUDIO_CHUNK_BYTES]
        if pending:
            yield bytes(pending)

    return _events_to_text(
        stt.run_stream(pcm_chunks(), timeout=REQUEST_TIMEOUT_SECONDS),
        on_partial=on_partial,
    )


def transcribe_audio(audio_data: Any, sample_rate: int = 16000, numpy_module=None) -> str:
    """Recognize a complete mono float audio array through SpeechKit v3."""
    if numpy_module is None:
        import numpy as numpy_module

    if sample_rate not in (8000, 16000, 48000):
        raise ValueError(f"SpeechKit v3 не поддерживает частоту {sample_rate} Гц в этом режиме.")

    audio = numpy_module.asarray(audio_data, dtype=numpy_module.float32).reshape(-1)
    if audio.size == 0:
        return ""
    pcm = (
        numpy_module.clip(audio, -1.0, 1.0) * 32767.0
    ).astype("<i2", copy=False).tobytes()
    if not pcm:
        return ""

    stt = _create_stt()
    chunks = [
        pcm[offset:offset + AUDIO_CHUNK_BYTES]
        for offset in range(0, len(pcm), AUDIO_CHUNK_BYTES)
    ]
    return _events_to_text(stt.run_stream(chunks, timeout=REQUEST_TIMEOUT_SECONDS))
