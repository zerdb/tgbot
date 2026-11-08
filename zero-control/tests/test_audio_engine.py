"""Тесты логики аудиодвижка без обращения к микрофону и GigaAM."""
import unittest
from unittest.mock import Mock

import numpy as np

from audio_engine import AudioEngine


class AudioEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = AudioEngine(
            get_ui=lambda: None,
            update_ui_status=lambda *args, **kwargs: None,
            handle_command=lambda text: None,
        )

    def test_transcribe_parts_splits_audio_at_configured_limit(self):
        audio = np.zeros(AudioEngine.SAMPLE_RATE * 25, dtype=np.float32)
        self.engine.transcribe_audio_file = Mock(side_effect=["первая часть", "вторая часть"])

        result = self.engine.transcribe_parts(audio, "фрагмент")

        self.assertEqual(result, "первая часть вторая часть")
        self.assertEqual(
            [call.args[0].size for call in self.engine.transcribe_audio_file.call_args_list],
            [AudioEngine.SAMPLE_RATE * 24, AudioEngine.SAMPLE_RATE],
        )

    def test_recording_state_properties(self):
        self.assertFalse(self.engine.is_recording)
        self.assertFalse(self.engine.is_dictation_active)

        self.engine._recording = True
        self.engine._recording_mode = "command"
        self.assertTrue(self.engine.is_recording)
        self.assertFalse(self.engine.is_dictation_active)

        self.engine._recording_mode = "text"
        self.assertTrue(self.engine.is_dictation_active)


if __name__ == "__main__":
    unittest.main()
