"""Groq Whisper transcription.

Sends WAV bytes to Groq's speech-to-text API and returns the transcript string.

Why response_format="text":
    The default JSON response wraps the text; "text" returns the raw string
    directly. Both work — "text" just skips the .text attribute access.
    We handle both return types defensively in case the SDK changes.
"""

import io

from groq import Groq


class Transcriber:
    def __init__(self, api_key: str, model: str = "whisper-large-v3"):
        self._client = Groq(api_key=api_key)
        self._model = model

    def transcribe(self, wav_bytes: bytes, language: str | None = None) -> str:
        """Send WAV bytes to Groq Whisper. Returns the transcript string.

        language: optional ISO-639-1 code (e.g. "en", "es"). When None,
        Whisper auto-detects — works well for most use cases.

        Raises groq.APIError on network or auth failure — caller should handle.
        """
        if not wav_bytes:
            return ""
        # The Groq SDK needs a file-like object with a .name attribute
        # so it can infer the content type from the extension.
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
        # SDK returns str when response_format="text", object otherwise
        return result.strip() if isinstance(result, str) else result.text.strip()
