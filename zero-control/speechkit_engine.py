"""Yandex SpeechKit synchronous speech recognition client."""
from __future__ import annotations

import os
from typing import Any

import requests


API_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
REQUEST_TIMEOUT_SECONDS = 45


def transcribe_audio(audio_data: Any, sample_rate: int = 16000, numpy_module=None) -> str:
    """Recognize mono float audio through SpeechKit using YC_API_KEY.

    Audio is sent as signed 16-bit little-endian PCM. The API key is read
    only from the process environment and is never persisted by this module.
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
        raise ValueError(f"SpeechKit не поддерживает частоту {sample_rate} Гц в этом режиме.")

    pcm = (
        numpy_module.clip(audio, -1.0, 1.0) * 32767.0
    ).astype("<i2", copy=False).tobytes()
    if not pcm:
        return ""

    headers = {"Authorization": f"Api-Key {api_key}"}
    params = {
        "topic": "general",
        "lang": "ru-RU",
        "format": "lpcm",
        "sampleRateHertz": str(sample_rate),
    }

    response = requests.post(
        API_URL,
        params=params,
        headers=headers,
        data=pcm,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    result = str(payload.get("result") or "").strip()
    return result
