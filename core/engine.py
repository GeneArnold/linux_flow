"""Central engine — owns recorder, transcriber, enhancer, injector, listener.

The UI and tray interact with this object rather than managing components directly.
Emits Python callbacks (not GTK signals) so it stays GTK-independent.
"""

import threading
import time
from typing import Callable

import config
from adapters.base import get_hotkey_listener, get_injector
from core.enhancer import Enhancer
from core.recorder import Recorder
from core.transcriber import Transcriber
from db import history as db

_WHISPER_HALLUCINATIONS = {
    ".",
    "..",
    "...",
    "you",
    "bye",
    "thanks",
    "thank you",
    "thank you.",
    "thanks.",
    "you.",
    "bye.",
    "goodbye.",
    "goodbye",
    "okay.",
    "okay",
    "ok.",
    "ok",
}


class Engine:
    def __init__(self):
        self._cfg = config.load()
        self._recorder: Recorder | None = None
        self._transcriber: Transcriber | None = None
        self._enhancer: Enhancer | None = None
        self._injector = None
        self._listener = None
        self._is_recording = threading.Event()
        self._start_time: float = 0.0

        # Callbacks the UI can subscribe to
        self.on_recording_start: Callable | None = None  # ()
        self.on_recording_stop: Callable | None = None  # ()
        self.on_result: Callable[[str, str, bool], None] | None = (
            None  # (raw, final, injected)
        )
        self.on_error: Callable[[str], None] | None = None  # (message)
        self.on_audio_level: Callable[[float], None] | None = None  # (rms)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Build all components and start the hotkey listener."""
        db.init()
        self._build_components()
        self._listener.start(self._on_press, self._on_release)

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()

    def reload(self) -> None:
        """Reload config and rebuild components (call after settings change)."""
        was_recording = self._is_recording.is_set()
        if was_recording:
            self._is_recording.clear()
        self.stop()
        self._cfg = config.load()
        self._build_components()
        self._listener.start(self._on_press, self._on_release)

    # ------------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------------

    def copy_last_transcript(self) -> str | None:
        """Return the most recent final_text and put it on the clipboard."""
        rows = db.get_recent(1)
        if not rows:
            return None
        text = rows[0]["final_text"]
        if self._injector:
            self._injector.copy_to_clipboard(text)
        return text

    @property
    def cfg(self) -> dict:
        return self._cfg

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_components(self) -> None:
        cfg = self._cfg
        self._recorder = Recorder(
            device_index=cfg["audio"]["device_index"],
            sample_rate=cfg["audio"]["sample_rate"],
            channels=cfg["audio"]["channels"],
        )
        self._recorder.on_level = self._level_cb

        self._transcriber = Transcriber(
            api_key=cfg["groq"]["api_key"],
            model=cfg["groq"]["whisper_model"],
        )
        self._enhancer = Enhancer(
            api_key=cfg["groq"]["api_key"],
            model=cfg["groq"]["llm_model"],
        )
        self._injector = get_injector()
        self._listener = get_hotkey_listener(
            modifiers=cfg["hotkey"]["modifiers"],
            key=cfg["hotkey"]["key"],
        )

    def _level_cb(self, rms: float) -> None:
        if self.on_audio_level:
            self.on_audio_level(rms)

    def _on_press(self) -> None:
        if self._is_recording.is_set():
            return
        self._is_recording.set()
        self._start_time = time.time()
        self._recorder.on_level = self._level_cb
        self._recorder.start()
        if self.on_recording_start:
            self.on_recording_start()

    def _on_release(self) -> None:
        if not self._is_recording.is_set():
            return
        self._is_recording.clear()
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self) -> None:
        if self.on_recording_stop:
            self.on_recording_stop()

        wav = self._recorder.stop()
        duration = time.time() - self._start_time

        if not wav:
            return

        try:
            raw = self._transcriber.transcribe(wav)
        except Exception as e:
            if self.on_error:
                self.on_error(str(e))
            return

        if not raw.strip() or raw.strip().lower() in _WHISPER_HALLUCINATIONS:
            return

        mode = self._cfg["enhancement"]["mode"]
        try:
            final = self._enhancer.enhance(raw, mode) if mode != "raw" else raw
        except Exception as e:
            final = raw
            if self.on_error:
                self.on_error(f"Enhancement failed, using raw: {e}")

        injected = False
        if self._cfg["output"]["auto_paste"]:
            injected = self._injector.inject(final)
            if not injected:
                self._injector.copy_to_clipboard(final)
        else:
            self._injector.copy_to_clipboard(final)

        if self._cfg["output"]["save_history"]:
            db.save(raw, final, mode, duration_s=duration, injected=injected)

        if self.on_result:
            self.on_result(raw, final, injected)
