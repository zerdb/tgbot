"""Unit tests for the Yandex SpeechKit HTTP client."""
import unittest
from unittest.mock import Mock, patch

import numpy as np

from speechkit_engine import transcribe_audio


class SpeechKitEngineTests(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_fails_without_network_request(self):
        with self.assertRaisesRegex(RuntimeError, "YC_API_KEY"):
            transcribe_audio(np.zeros(160, dtype=np.float32), numpy_module=np)

    @patch.dict("os.environ", {"YC_API_KEY": "test-secret"})
    @patch("speechkit_engine.requests.post")
    def test_sends_mono_pcm_and_returns_recognized_text(self, post):
        response = Mock()
        response.json.return_value = {"result": "проверка связи"}
        post.return_value = response

        result = transcribe_audio(
            np.array([0.0, 1.0, -1.0], dtype=np.float32),
            sample_rate=16000,
            numpy_module=np,
        )

        self.assertEqual(result, "проверка связи")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize")
        self.assertEqual(kwargs["headers"]["Authorization"], "Api-Key test-secret")
        self.assertEqual(kwargs["params"]["format"], "lpcm")
        self.assertEqual(kwargs["params"]["sampleRateHertz"], "16000")
        self.assertEqual(kwargs["data"], b"\x00\x00\xff\x7f\x01\x80")
        self.assertEqual(kwargs["timeout"], 45)
        response.raise_for_status.assert_called_once_with()

    @patch.dict("os.environ", {"YC_API_KEY": "test-secret"})
    @patch("speechkit_engine.requests.post")
    def test_rejects_unsupported_sample_rate(self, post):
        with self.assertRaisesRegex(ValueError, "частоту"):
            transcribe_audio(
                np.zeros(10, dtype=np.float32),
                sample_rate=44100,
                numpy_module=np,
            )
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
