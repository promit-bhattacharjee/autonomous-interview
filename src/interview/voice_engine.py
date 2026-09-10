"""
[LEGACY / TERMINAL PROTOTYPE ONLY]
Voice Engine for UK Credibility & Academic Interviewer.
Provides text-to-speech (TTS) playback and microphone speech-to-text (STT) recording
using Google GenAI Gemini models and sounddevice for local terminal execution.

DEPRECATION NOTICE:
In the web application architecture (FastAPI + LiveKit direct WebRTC),
this module is superseded by `interview.live_kit.agent.py` which handles
audio streaming over WebRTC via Silero VAD, Gemini STT, and Gemini TTS.
Host OS audio hardware (`sounddevice`) is neither used nor required in Docker/production.
"""

import io
import logging
import os
import sys
import threading
import time
import wave
from typing import Optional, Tuple

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("interview-voice-engine")

DEFAULT_SAMPLE_RATE = 24000
DEFAULT_VOICE = "Aoede"  # Aoede: Warm, clear, professional tone for UK interviewer
TTS_MODEL_PRIMARY = "gemini-2.5-flash-preview-tts"
TTS_MODEL_FALLBACK = "gemini-3.1-flash-tts-preview"
STT_MODEL = "gemini-3.6-flash"


def _get_genai_client():
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY not configured in environment or .env file.")
    from google.genai import Client

    return Client(api_key=api_key)


def get_audio_device_info() -> dict:
    """Returns detected default audio input and output devices."""
    try:
        input_dev = sd.query_devices(kind="input")
        output_dev = sd.query_devices(kind="output")
        return {
            "has_input": True,
            "has_output": True,
            "input_name": input_dev.get("name", "Unknown Input"),
            "output_name": output_dev.get("name", "Unknown Output"),
        }
    except Exception as e:
        logger.warning(f"Failed to query audio hardware: {e}")
        return {
            "has_input": False,
            "has_output": False,
            "input_name": "Unavailable",
            "output_name": "Unavailable",
        }


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE, channels: int = 1) -> bytes:
    """Wraps raw 16-bit PCM audio bytes in a standard WAV header."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return wav_io.getvalue()


def speak_text(
    text: str,
    voice_name: str = DEFAULT_VOICE,
    instructions: str = "Speak clearly, warmly, and at a measured pace like a professional UK university interviewer.",
) -> bool:
    """
    Synthesizes speech using Google Gemini TTS and plays it directly
    through the system's default output device.
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return False

    try:
        client = _get_genai_client()
        from google.genai import types

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
        )

        prompt_content = f"{instructions}\n\n{clean_text}" if instructions else clean_text

        raw_pcm = None
        for model in [TTS_MODEL_PRIMARY, TTS_MODEL_FALLBACK]:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt_content,
                    config=config,
                )
                if response.candidates and response.candidates[0].content:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.data:
                            raw_pcm = part.inline_data.data
                            break
                if raw_pcm:
                    break
            except Exception as model_err:
                logger.debug(f"TTS attempt with {model} failed: {model_err}")
                continue

        if not raw_pcm:
            logger.warning("No audio data returned by Gemini TTS.")
            return False

        # Convert PCM 16-bit buffer to numpy array and play via sounddevice
        audio_array = np.frombuffer(raw_pcm, dtype=np.int16)
        sd.play(audio_array, samplerate=DEFAULT_SAMPLE_RATE)
        sd.wait()
        return True

    except Exception as e:
        logger.error(f"Voice playback failed: {e}")
        return False


def record_candidate_speech(
    prompt_message: str = "🔴 Recording started... Speak your answer now.",
) -> str:
    """
    Records audio from the candidate's microphone until the candidate presses [ENTER].
    Transcribes the recorded audio using Gemini Multimodal STT and returns the transcript.
    """
    try:
        client = _get_genai_client()
        from google.genai import types
    except Exception as e:
        logger.error(f"Cannot initialize GenAI client for STT: {e}")
        return ""

    recorded_chunks = []
    stop_event = threading.Event()

    def _audio_callback(indata, frames, time_info, status):
        if not stop_event.is_set():
            recorded_chunks.append(indata.copy())

    print(f"\n{prompt_message}")
    print("👉 Speak naturally into your microphone. When you are finished, press [ENTER] to submit:")

    try:
        stream = sd.InputStream(
            samplerate=DEFAULT_SAMPLE_RATE,
            channels=1,
            dtype="int16",
            callback=_audio_callback,
        )
        with stream:
            # Wait for candidate to press Enter
            input()
            stop_event.set()
    except Exception as e:
        logger.error(f"Microphone recording failed: {e}")
        return ""

    if not recorded_chunks:
        print("[-] No audio captured from microphone.")
        return ""

    # Concatenate all recorded chunks into contiguous PCM buffer
    full_audio = np.concatenate(recorded_chunks, axis=0)
    pcm_bytes = full_audio.tobytes()

    # Check for non-trivial audio capture
    max_amp = np.max(np.abs(full_audio)) if len(full_audio) > 0 else 0
    if max_amp < 50 or len(pcm_bytes) < (DEFAULT_SAMPLE_RATE * 2 * 0.5):  # Under 0.5s or near dead silence
        print("[-] Microphone input was too quiet or too short to transcribe.")
        return ""

    wav_bytes = pcm_to_wav(pcm_bytes, sample_rate=DEFAULT_SAMPLE_RATE, channels=1)

    print("\n[+] Transcribing your spoken response with Gemini AI...")
    try:
        stt_response = client.models.generate_content(
            model=STT_MODEL,
            contents=[
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                "Transcribe this candidate interview response word-for-word. "
                "Output ONLY the exact spoken transcription text. Do not add explanations or formatting.",
            ],
        )
        transcribed_text = (stt_response.text or "").strip()
        return transcribed_text
    except Exception as stt_err:
        logger.error(f"Speech transcription failed: {stt_err}")
        return ""
