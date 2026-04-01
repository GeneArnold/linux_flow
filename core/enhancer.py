"""Groq LLM text enhancement.

Modes:
  raw     - return transcript unchanged
  clean   - fix grammar, punctuation, remove filler words
  rewrite - turn rambling speech into polished prose
"""

from groq import Groq

_PROMPTS = {
    "clean": (
        "You are a transcription editor. The user dictated the following text. "
        "Fix grammar, punctuation, and capitalization. Remove filler words like "
        "'um', 'uh', 'you know', 'like'. Keep the meaning and tone identical. "
        "Return ONLY the corrected text, nothing else."
    ),
    "rewrite": (
        "You are a professional writer. The user dictated the following rough speech. "
        "Rewrite it as clear, polished prose. Preserve the core meaning and intent. "
        "Return ONLY the rewritten text, nothing else."
    ),
}


class Enhancer:
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self._client = Groq(api_key=api_key)
        self._model = model

    def enhance(self, text: str, mode: str = "clean") -> str:
        if mode == "raw" or not text.strip():
            return text

        system_prompt = _PROMPTS.get(mode, _PROMPTS["clean"])
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        result = response.choices[0].message.content.strip()

        # Guard: if the LLM returned a meta-response instead of actual text, use raw
        _meta_phrases = (
            "there is no text",
            "nothing to correct",
            "no text to",
            "text is empty",
            "no input",
        )
        if any(p in result.lower() for p in _meta_phrases):
            return text

        return result
