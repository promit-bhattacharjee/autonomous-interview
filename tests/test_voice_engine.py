import io
import sys
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

src_path = str(Path(__file__).resolve().parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from interview.voice_engine import (
    DEFAULT_SAMPLE_RATE,
    get_audio_device_info,
    pcm_to_wav,
    record_candidate_speech,
    speak_text,
)


class TestVoiceEngine(unittest.TestCase):
    """Unit tests for the voice engine (TTS, STT, audio devices, and WAV containers)."""

    def test_pcm_to_wav_formatting(self):
        """Verifies that pcm_to_wav generates a standard 16-bit mono WAV container."""
        pcm_data = (np.sin(np.linspace(0, 1, 2400)) * 10000).astype(np.int16).tobytes()
        wav_bytes = pcm_to_wav(pcm_data, sample_rate=24000, channels=1)

        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav_bytes[:16])

        # Read back with standard wave module to verify integrity
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getframerate(), 24000)
            self.assertEqual(wf.getnframes(), 2400)

    @patch("interview.voice_engine.sd.query_devices")
    def test_get_audio_device_info_success(self, mock_query):
        """Returns detected input and output device names."""
        mock_query.side_effect = lambda kind: {
            "input": {"name": "Microphone (Realtek)"},
            "output": {"name": "Headphones (Realtek)"},
        }[kind]

        info = get_audio_device_info()
        self.assertTrue(info["has_input"])
        self.assertTrue(info["has_output"])
        self.assertEqual(info["input_name"], "Microphone (Realtek)")
        self.assertEqual(info["output_name"], "Headphones (Realtek)")

    @patch("interview.voice_engine.sd.query_devices", side_effect=RuntimeError("No audio host"))
    def test_get_audio_device_info_error_handling(self, mock_query):
        """Handles audio query errors gracefully without raising exceptions."""
        info = get_audio_device_info()
        self.assertFalse(info["has_input"])
        self.assertFalse(info["has_output"])
        self.assertEqual(info["input_name"], "Unavailable")

    def test_speak_text_empty_input(self):
        """Returns False early if text is empty or whitespace."""
        self.assertFalse(speak_text(""))
        self.assertFalse(speak_text("   "))
        self.assertFalse(speak_text(None))

    @patch("interview.voice_engine._get_genai_client")
    @patch("interview.voice_engine.sd.play")
    @patch("interview.voice_engine.sd.wait")
    def test_speak_text_successful_playback(self, mock_wait, mock_play, mock_get_client):
        """Synthesizes PCM audio and plays via sounddevice."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_candidate = MagicMock()
        mock_part = MagicMock()
        mock_part.inline_data.data = np.zeros(2400, dtype=np.int16).tobytes()
        mock_candidate.content.parts = [mock_part]
        mock_client.models.generate_content.return_value = MagicMock(candidates=[mock_candidate])

        result = speak_text("Why did you choose the University of Hertfordshire?")
        self.assertTrue(result)
        mock_play.assert_called_once()
        mock_wait.assert_called_once()

    @patch("interview.voice_engine._get_genai_client")
    @patch("interview.voice_engine.sd.play")
    @patch("interview.voice_engine.sd.wait")
    def test_speak_text_fallback_model_on_primary_failure(self, mock_wait, mock_play, mock_get_client):
        """Falls back to secondary TTS model if primary model fails."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # First call (primary model) raises, second call (fallback) succeeds
        mock_candidate = MagicMock()
        mock_part = MagicMock()
        mock_part.inline_data.data = np.zeros(1200, dtype=np.int16).tobytes()
        mock_candidate.content.parts = [mock_part]
        success_response = MagicMock(candidates=[mock_candidate])

        mock_client.models.generate_content.side_effect = [
            RuntimeError("Primary model unavailable"),
            success_response,
        ]

        result = speak_text("Testing fallback")
        self.assertTrue(result)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        mock_play.assert_called_once()

    @patch("builtins.input", return_value="")
    @patch("interview.voice_engine.sd.InputStream")
    @patch("interview.voice_engine._get_genai_client")
    def test_record_candidate_speech_empty_audio_returns_empty(self, mock_get_client, mock_stream, mock_input):
        """Returns empty string if microphone captured no audible audio."""
        mock_get_client.return_value = MagicMock()
        # Mock stream that collects no chunks
        mock_stream.return_value.__enter__.return_value = MagicMock()

        transcript = record_candidate_speech()
        self.assertEqual(transcript, "")

    @patch("builtins.input", return_value="")
    @patch("interview.voice_engine.sd.InputStream")
    @patch("interview.voice_engine._get_genai_client")
    def test_record_candidate_speech_success(self, mock_get_client, mock_stream, mock_input):
        """Captures candidate microphone audio and transcribes via Gemini STT."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock STT transcription response
        mock_response = MagicMock(text="I selected the MSc Artificial Intelligence because of module 7COM1076.")
        mock_client.models.generate_content.return_value = mock_response

        # Simulate stream callback pushing valid audio chunks
        def fake_enter(self_mock):
            callback = mock_stream.call_args[1]["callback"]
            # Generate 1 second of audible audio at 24kHz
            audio_chunk = (np.sin(np.linspace(0, 10, 24000)) * 5000).astype(np.int16).reshape(-1, 1)
            callback(audio_chunk, 24000, None, None)
            return self_mock

        mock_stream.return_value.__enter__.side_effect = lambda: fake_enter(mock_stream.return_value)

        transcript = record_candidate_speech()
        self.assertEqual(transcript, "I selected the MSc Artificial Intelligence because of module 7COM1076.")
        mock_client.models.generate_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
