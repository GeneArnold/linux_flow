"""Groq LLM text enhancement.

Takes raw Whisper transcript and optionally cleans or rewrites it using Llama.

Modes:
  raw     — return transcript completely unchanged (no API call)
  clean   — fix grammar, punctuation, remove filler words ("um", "uh", etc.)
  rewrite — turn rambling speech into polished, well-structured prose

Why the meta-response guard exists:
    When Whisper returns very short or odd text (e.g. a single punctuation mark
    that slipped past the hallucination filter), Llama may respond with a
    message like "There is no text to correct" instead of the corrected text.
    We detect these meta-phrases and fall back to the raw transcript so the
    user doesn't have that sentence injected into their document.
"""

from groq import Groq

_DEFAULT_PROMPTS = {
    "clean": (
        "You are a transcription editor. The user dictated the following text. "
        "Add correct punctuation and capitalization. Remove filler words like "
        "'um', 'uh', 'you know', 'like'. Do NOT change any words, fix grammar, "
        "or restructure sentences — only add punctuation and capitalization. "
        "Return ONLY the corrected text, nothing else."
    ),
    "rewrite": (
        "You are a professional writer. The user dictated the following rough speech. "
        "Fix grammar, restructure sentences, and rewrite it as clear, polished prose. "
        "Combine fragments, improve flow, and tighten wording. "
        "Preserve the core meaning and intent. "
        "Return ONLY the rewritten text, nothing else."
    ),
}

# Phrases that indicate the LLM returned a meta-response instead of enhanced text.
# If detected, we return the original raw transcript instead.
_META_PHRASES = (
    "there is no text",
    "nothing to correct",
    "no text to",
    "text is empty",
    "no input",
)


class Enhancer:
    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        prompts: dict[str, str] | None = None,
    ):
        self._client = Groq(api_key=api_key)
        self._model = model
        self._prompts = prompts or _DEFAULT_PROMPTS

    def enhance(self, text: str, mode: str = "clean") -> str:
        """Enhance the transcript according to mode.

        Returns the enhanced text, or the original text if mode is "raw",
        the input is empty, or the LLM returns a meta-response.

        Raises groq.APIError on network or auth failure — caller should handle.
        """
        if mode == "raw" or not text.strip():
            return text

        system_prompt = self._prompts.get(mode, self._prompts["clean"])
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.3,  # low temperature = more consistent editing
            max_tokens=1024,
        )
        result = response.choices[0].message.content.strip()

        # Guard: fall back to raw if Llama returned a meta-response
        if any(p in result.lower() for p in _META_PHRASES):
            return text

        return result
