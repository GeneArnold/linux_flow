"""Groq Whisper transcription."""

import io

from groq import Groq


class Transcriber:
    def __init__(self, api_key: str, model: str = "whisper-large-v3"):
        self._client = Groq(api_key=api_key)
        self._model = model

    def transcribe(self, wav_bytes: bytes, language: str | None = None) -> str:
        """Send WAV bytes to Groq Whisper. Returns transcript string."""
        if not wav_bytes:
            return ""
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "audio.wav"
        kwargs = {
            "file": audio_file,
            "model": self._model,
            "response_format": "text",
        }
        if language:
            kwargs["language"] = language
        result = self._client.audio.transcriptions.create(**kwargs)
        return result.strip() if isinstance(result, str) else result.text.strip()
