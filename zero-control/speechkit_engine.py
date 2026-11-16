"""Yandex SpeechKit Recognition API v3 streaming client."""
from __future__ import annotations

import asyncio
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


def _create_async_stt():
    api_key = os.getenv("YC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Не найден YC_API_KEY. Добавьте ключ Yandex Cloud в переменные "
            "окружения Windows и перезапустите Zero Control."
        )
    from yandex_ai_studio_sdk import AsyncAIStudio

    folder_id = os.getenv("YC_FOLDER_ID", "").strip() or API_FOLDER_ID
    sdk = AsyncAIStudio(auth=api_key, folder_id=folder_id)
    return sdk.speechkit.speech_to_text(
        model="general",
        audio_format=sdk.speechkit.AudioFormat.PCM16(16000),
        language_codes="ru-RU",
        text_normalization=True,
    )


class _SpeechEventCollector:
    def __init__(self, on_partial: Callable[[str], None] | None = None):
        self.final_texts = []
        self.refined_texts = []
        self.latest_partial = ""
        self.on_partial = on_partial

    def add(self, event: Any) -> None:
        if event.event_type == "partial":
            partial = (event.partial_text or "").strip()
            if partial and partial != self.latest_partial:
                self.latest_partial = partial
                print(f"[SpeechKit v3] {partial}", flush=True)
                if self.on_partial is not None:
                    self.on_partial(partial)
        elif event.event_type == "final":
            value = (event.final_text or "").strip()
            if value:
                self.final_texts.append(value)
                self.latest_partial = ""
                if self.on_partial is not None:
                    self.on_partial(" ".join(self.final_texts))
        elif event.event_type == "final_refinement":
            value = (event.final_refinement_text or "").strip()
            if value:
                self.refined_texts.append(value)

    def result(self) -> str:
        result = self.refined_texts or self.final_texts
        return " ".join(part.strip() for part in result if part.strip()).strip()


def _events_to_text(
    events: Iterable[Any],
    on_partial: Callable[[str], None] | None = None,
) -> str:
    collector = _SpeechEventCollector(on_partial)
    for event in events:
        collector.add(event)
    return collector.result()


def transcribe_audio_stream(
    audio_queue,
    stop_token,
    numpy_module=None,
    on_partial: Callable[[str], None] | None = None,
) -> str:
    """Send microphone PCM chunks through the SDK's true bidirectional stream.

    The producer puts mono float32 numpy arrays into audio_queue and puts
    stop_token after the microphone stream has been closed.
    """
    if numpy_module is None:
        import numpy as numpy_module

    import queue

    async def run_stream() -> str:
        stt = _create_async_stt()
        stream = stt.create_bistream(timeout=REQUEST_TIMEOUT_SECONDS)
        collector = _SpeechEventCollector(on_partial)

        async def send_audio() -> None:
            pending = bytearray()
            stopped = False
            while not stopped:
                try:
                    block = audio_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.01)
                    continue

                if block is stop_token:
                    stopped = True
                    break

                audio = numpy_module.asarray(
                    block, dtype=numpy_module.float32
                ).reshape(-1)
                if audio.size:
                    pcm = (
                        numpy_module.clip(audio, -1.0, 1.0) * 32767.0
                    ).astype("<i2", copy=False).tobytes()
                    pending.extend(pcm)
                    while len(pending) >= AUDIO_CHUNK_BYTES:
                        await stream.write(bytes(pending[:AUDIO_CHUNK_BYTES]))
                        del pending[:AUDIO_CHUNK_BYTES]

            if pending:
                await stream.write(bytes(pending))
            await stream.done_writing()

        async def receive_events() -> None:
            async for event in stream.gen():
                collector.add(event)

        await asyncio.gather(send_audio(), receive_events())
        return collector.result()

    return asyncio.run(run_stream())


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
