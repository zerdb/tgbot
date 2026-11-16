"""Unit tests for the Yandex SpeechKit v3 streaming client."""
import contextlib
import io
import os
import queue
import sys
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np

from speechkit_engine import transcribe_audio, transcribe_audio_stream


class SpeechKitEngineTests(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_fails_without_sdk_initialization(self):
        with self.assertRaisesRegex(RuntimeError, "YC_API_KEY"):
            transcribe_audio(np.zeros(160, dtype=np.float32), numpy_module=np)

    def test_v3_streaming_sends_pcm_chunks_and_returns_refined_text(self):
        events = [
            types.SimpleNamespace(event_type="partial", partial_text="проверка"),
            types.SimpleNamespace(event_type="final", final_text="проверка связи"),
            types.SimpleNamespace(
                event_type="final_refinement",
                final_refinement_text="Проверка связи.",
            ),
        ]
        stt = Mock()
        stt.run_stream.return_value = iter(events)
        sdk = Mock()
        sdk.speechkit.AudioFormat.PCM16.return_value = "pcm16-format"
        sdk.speechkit.speech_to_text.return_value = stt
        sdk_module = types.SimpleNamespace(AIStudio=Mock(return_value=sdk))

        with patch.dict(os.environ, {"YC_API_KEY": "test-secret"}, clear=True):
            with patch.dict(sys.modules, {"yandex_ai_studio_sdk": sdk_module}):
                result = transcribe_audio(
                    np.array([0.0, 1.0, -1.0], dtype=np.float32),
                    sample_rate=16000,
                    numpy_module=np,
                )

        self.assertEqual(result, "Проверка связи.")
        sdk_module.AIStudio.assert_called_once_with(
            auth="test-secret",
            folder_id="b1gfpt3ceq4e2au6p5md",
        )
        sdk.speechkit.speech_to_text.assert_called_once_with(
            model="general",
            audio_format="pcm16-format",
            language_codes="ru-RU",
            text_normalization=True,
        )
        args, kwargs = stt.run_stream.call_args
        self.assertEqual(kwargs["timeout"], 90)
        self.assertEqual(args[0], [bytes([0, 0, 255, 127, 1, 128])])

    @patch.dict("os.environ", {"YC_API_KEY": "test-secret"})
    def test_custom_folder_id_is_used(self):
        stt = Mock()
        stt.run_stream.return_value = iter([])
        sdk = Mock()
        sdk.speechkit.AudioFormat.PCM16.return_value = "pcm16"
        sdk.speechkit.speech_to_text.return_value = stt
        sdk_module = types.SimpleNamespace(AIStudio=Mock(return_value=sdk))

        with patch.dict(os.environ, {"YC_FOLDER_ID": "custom-folder"}):
            with patch.dict(sys.modules, {"yandex_ai_studio_sdk": sdk_module}):
                transcribe_audio(np.zeros(10, dtype=np.float32), numpy_module=np)

        sdk_module.AIStudio.assert_called_once_with(
            auth="test-secret",
            folder_id="custom-folder",
        )

    @patch.dict("os.environ", {"YC_API_KEY": "test-secret"})
    def test_rejects_unsupported_sample_rate_before_sdk_initialization(self):
        with self.assertRaisesRegex(ValueError, "частоту"):
            transcribe_audio(
                np.zeros(10, dtype=np.float32),
                sample_rate=44100,
                numpy_module=np,
            )

    def test_live_stream_uses_bidirectional_sdk_and_reports_partial_text(self):
        audio_queue = queue.Queue()
        stop_token = object()
        audio_queue.put(np.zeros(6400, dtype=np.float32))
        audio_queue.put(stop_token)
        partials = []

        class FakeStream:
            def __init__(self):
                self.written = []
                self.closed = False

            async def write(self, data):
                self.written.append(data)

            async def done_writing(self):
                self.closed = True

            async def gen(self):
                while not self.closed:
                    import asyncio
                    await asyncio.sleep(0)
                yield types.SimpleNamespace(
                    event_type="partial", partial_text="потоковая проверка"
                )
                yield types.SimpleNamespace(
                    event_type="final", final_text="потоковая проверка"
                )
                yield types.SimpleNamespace(
                    event_type="final_refinement",
                    final_refinement_text="Потоковая проверка.",
                )

        fake_stream = FakeStream()
        stt = Mock()
        stt.create_bistream.return_value = fake_stream
        sdk = Mock()
        sdk.speechkit.AudioFormat.PCM16.return_value = "pcm16"
        sdk.speechkit.speech_to_text.return_value = stt
        sdk_module = types.SimpleNamespace(AsyncAIStudio=Mock(return_value=sdk))
        retry_module = types.SimpleNamespace(NoRetryPolicy=Mock(return_value="no-retry"))

        with patch.dict(os.environ, {"YC_API_KEY": "test-secret"}, clear=True):
            with patch.dict(
                sys.modules,
                {
                    "yandex_ai_studio_sdk": sdk_module,
                    "yandex_ai_studio_sdk._retry": retry_module,
                },
            ):
                result = transcribe_audio_stream(
                    audio_queue,
                    stop_token,
                    numpy_module=np,
                    on_partial=partials.append,
                )

        self.assertEqual(result, "Потоковая проверка.")
        self.assertEqual(fake_stream.written, [bytes(12800)])
        self.assertEqual(
            partials,
            ["потоковая проверка", "потоковая проверка"],
        )
        sdk_module.AsyncAIStudio.assert_called_once_with(
            auth="test-secret",
            folder_id="b1gfpt3ceq4e2au6p5md",
            retry_policy="no-retry",
        )
        stt.create_bistream.assert_called_once_with(timeout=90)

    def test_live_stream_reports_original_rpc_error_and_cancels_sender(self):
        audio_queue = queue.Queue()
        stop_token = object()
        partials = []

        class FakeStream:
            async def write(self, data):
                raise RuntimeError("RPC already finished")

            async def done_writing(self):
                pass

            async def gen(self):
                while True:
                    await __import__("asyncio").sleep(1)
                    yield None

        stt = Mock()
        stt.create_bistream.return_value = FakeStream()
        sdk = Mock()
        sdk.speechkit.AudioFormat.PCM16.return_value = "pcm16"
        sdk.speechkit.speech_to_text.return_value = stt
        sdk_module = types.SimpleNamespace(AsyncAIStudio=Mock(return_value=sdk))
        retry_module = types.SimpleNamespace(NoRetryPolicy=Mock(return_value="no-retry"))
        audio_queue.put(np.zeros(6400, dtype=np.float32))
        audio_queue.put(stop_token)

        output = io.StringIO()
        with patch.dict(os.environ, {"YC_API_KEY": "test-secret"}, clear=True):
            with patch.dict(
                sys.modules,
                {
                    "yandex_ai_studio_sdk": sdk_module,
                    "yandex_ai_studio_sdk._retry": retry_module,
                },
            ):
                with contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(RuntimeError, "RPC already finished"):
                        transcribe_audio_stream(
                            audio_queue, stop_token, numpy_module=np
                        )

        self.assertIn("Ошибка двустороннего gRPC-потока", output.getvalue())
        self.assertIn("RuntimeError: RPC already finished", output.getvalue())


if __name__ == "__main__":
    unittest.main()
