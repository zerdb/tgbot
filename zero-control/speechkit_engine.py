"""Yandex SpeechKit Recognition API v3 streaming client."""
from __future__ import annotations

import os
from typing import Any

API_FOLDER_ID = "b1gfpt3ceq4e2au6p5md"
AUDIO_CHUNK_BYTES = 4000
REQUEST_TIMEOUT_SECONDS = 90


def transcribe_audio(audio_data: Any, sample_rate: int = 16000, numpy_module=None) -> str:
    """Recognize mono float audio through the SpeechKit v3 gRPC streaming API.

    The API key is read from the process environment and is never persisted.
    Audio is uploaded as small LPCM chunks; partial hypotheses are reported
    while the gRPC stream is being processed.
    """
    api_key = os.getenv("YC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Не найден YC_API_KEY. Добавьте ключ Yandex Cloud в переменные "
            "окружения Windows и перезапустите Zero Control."
        )

    if numpy_module is None:
        import numpy as numpy_module

    audio = numpy_module.asarray(audio_data, dtype=numpy_module.float32).reshape(-1)
    if audio.size == 0:
        return ""
    if sample_rate not in (8000, 16000, 48000):
        raise ValueError(f"SpeechKit v3 не поддерживает частоту {sample_rate} Гц в этом режиме.")

    pcm = (
        numpy_module.clip(audio, -1.0, 1.0) * 32767.0
    ).astype("<i2", copy=False).tobytes()
    if not pcm:
        return ""

    from yandex_ai_studio_sdk import AIStudio

    folder_id = os.getenv("YC_FOLDER_ID", "").strip() or API_FOLDER_ID
    sdk = AIStudio(auth=api_key, folder_id=folder_id)
    stt = sdk.speechkit.speech_to_text(
        model="general",
        audio_format=sdk.speechkit.AudioFormat.PCM16(sample_rate),
        language_codes="ru-RU",
        text_normalization=True,
    )
    chunks = [
        pcm[offset:offset + AUDIO_CHUNK_BYTES]
        for offset in range(0, len(pcm), AUDIO_CHUNK_BYTES)
    ]

    final_texts = []
    refined_texts = []
    latest_partial = ""
    for event in stt.run_stream(chunks, timeout=REQUEST_TIMEOUT_SECONDS):
        if event.event_type == "partial":
            partial = event.partial_text or ""
            if partial and partial != latest_partial:
                latest_partial = partial
                print(f"[SpeechKit v3] {partial}", flush=True)
        elif event.event_type == "final":
            value = event.final_text or ""
            if value:
                final_texts.append(value)
                latest_partial = ""
        elif event.event_type == "final_refinement":
            value = event.final_refinement_text or ""
            if value:
                refined_texts.append(value)

    # Prefer normalized final results; otherwise use the fixed final hypotheses.
    result = refined_texts or final_texts
    return " ".join(part.strip() for part in result if part.strip()).strip()
