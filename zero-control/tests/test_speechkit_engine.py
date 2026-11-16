"""Unit tests for the Yandex SpeechKit v3 streaming client."""
import os
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


    def test_live_stream_consumes_microphone_queue_and_reports_partial_text(self):
        import queue
        audio_queue = queue.Queue()
        stop_token = object()
        audio_queue.put(np.zeros(6400, dtype=np.float32))
        audio_queue.put(stop_token)
        partials = []
        stt = Mock()
        def consume(chunks, timeout):
            sent = list(chunks)
            self.assertEqual(timeout, 90)
            self.assertEqual(len(sent), 1)
            self.assertEqual(len(sent[0]), 12800)
            return iter([
                types.SimpleNamespace(event_type="partial", partial_text="потоковая проверка"),
                types.SimpleNamespace(event_type="final", final_text="потоковая проверка"),
                types.SimpleNamespace(event_type="final_refinement", final_refinement_text="Потоковая проверка."),
            ])
        stt.run_stream.side_effect = consume
        sdk = Mock()
        sdk.speechkit.AudioFormat.PCM16.return_value = "pcm16"
        sdk.speechkit.speech_to_text.return_value = stt
        sdk_module = types.SimpleNamespace(AIStudio=Mock(return_value=sdk))
        with patch.dict(os.environ, {"YC_API_KEY": "test-secret"}, clear=True):
            with patch.dict(sys.modules, {"yandex_ai_studio_sdk": sdk_module}):
                result = transcribe_audio_stream(audio_queue, stop_token, numpy_module=np, on_partial=partials.append)
        self.assertEqual(result, "Потоковая проверка.")
        self.assertEqual(partials, ["потоковая проверка", "потоковая проверка"])
if __name__ == "__main__":
    unittest.main()
