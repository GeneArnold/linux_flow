"""Central orchestration engine for Linux Flow.

This is the heart of the app. It owns all the worker objects and coordinates
the full record → transcribe → enhance → inject pipeline.

Architecture:
    Engine
    ├── Recorder        — captures mic audio via sounddevice
    ├── Transcriber     — sends WAV to Groq Whisper
    ├── Enhancer        — optionally sends text to Groq Llama
    ├── TextInjector    — types the result into the active window (xdotool)
    └── HotkeyListener  — watches for the hotkey combo (pynput on X11)

Threading model:
    - HotkeyListener runs its own pynput thread (always live)
    - _on_press/_on_release are called from that pynput thread
    - _process() runs in a fresh daemon thread per recording so the hotkey
      listener is never blocked by the network calls

Callback contract (all UI callbacks must use GLib.idle_add for GTK safety):
    on_recording_start()            — hotkey pressed, mic open
    on_recording_stop()             — hotkey released, processing begins
    on_result(raw, final, injected) — pipeline complete
    on_error(message)               — any stage failed
    on_audio_level(rms)             — per-chunk RMS for the waveform overlay
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

# Whisper sometimes returns these when given silence or very short audio.
# Discard them rather than injecting a meaningless word into the user's document.
_WHISPER_HALLUCINATIONS = {
    ".",
    "..",
    "...",
    "you",
    "you.",
    "bye",
    "bye.",
    "goodbye",
    "goodbye.",
    "thanks",
    "thanks.",
    "thank you",
    "thank you.",
    "okay",
    "okay.",
    "ok",
    "ok.",
}


class Engine:
    def __init__(self):
        self._cfg = config.load()

        # Worker objects — built (or rebuilt) by _build_components()
        self._recorder: Recorder | None = None
        self._transcriber: Transcriber | None = None
        self._enhancer: Enhancer | None = None
        self._injector = None
        self._listener = None

        self._is_recording = threading.Event()
        self._start_time: float = 0.0

        # UI callbacks — set by the app layer after construction.
        # All are optional; check before calling.
        self.on_recording_start: Callable | None = None  # ()
        self.on_recording_stop: Callable | None = None  # ()
        self.on_result: Callable[[str, str, bool], None] | None = (
            None  # (raw, final, injected)
        )
        self.on_error: Callable[[str], None] | None = None  # (message)
        self.on_audio_level: Callable[[float], None] | None = None  # (rms float)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise the DB, build all components, and start listening for hotkeys."""
        db.init()
        self._build_components()
        self._listener.start(self._on_press, self._on_release)

    def stop(self) -> None:
        """Stop the hotkey listener. Safe to call when already stopped."""
        if self._listener:
            self._listener.stop()

    def reload(self) -> None:
        """Re-read config and rebuild all components.

        Called by UI settings pages after any setting changes. The listener
        is restarted with the potentially new hotkey combo.
        """
        # Clear the recording flag in case we're reloading mid-session
        self._is_recording.clear()
        self.stop()
        self._cfg = config.load()
        self._build_components()
        self._listener.start(self._on_press, self._on_release)

    # ------------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------------

    def copy_last_transcript(self) -> str | None:
        """Put the most recent transcript on the clipboard and return it.
        Returns None if history is empty.
        """
        rows = db.get_recent(1)
        if not rows:
            return None
        text = rows[0]["final_text"]
        if self._injector:
            self._injector.copy_to_clipboard(text)
        return text

    @property
    def cfg(self) -> dict:
        """Read-only access to the current config dict."""
        return self._cfg

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_components(self) -> None:
        """Instantiate all worker objects from the current config."""
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
            prompts={
                "clean": cfg["enhancement"]["prompt_clean"],
                "rewrite": cfg["enhancement"]["prompt_rewrite"],
            },
        )
        self._injector = get_injector()
        self._listener = get_hotkey_listener(
            modifiers=cfg["hotkey"]["modifiers"],
            key=cfg["hotkey"]["key"],
        )

    def _level_cb(self, rms: float) -> None:
        """Forward audio level to the UI overlay (waveform visualiser)."""
        if self.on_audio_level:
            self.on_audio_level(rms)

    def _on_press(self) -> None:
        """Called from the pynput thread when the hotkey is pressed down."""
        if self._is_recording.is_set():
            return  # guard against double-press
        self._is_recording.set()
        self._start_time = time.time()
        self._recorder.on_level = self._level_cb
        self._recorder.start()
        if self.on_recording_start:
            self.on_recording_start()

    def _on_release(self) -> None:
        """Called from the pynput thread when the hotkey is released.
        Kicks off the async pipeline in a daemon thread so the hotkey listener
        is never blocked by Groq API latency.
        """
        if not self._is_recording.is_set():
            return
        self._is_recording.clear()
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self) -> None:
        """Full pipeline: stop mic → transcribe → enhance → inject → save.
        Runs in its own daemon thread. Any stage can fail independently.
        """
        if self.on_recording_stop:
            self.on_recording_stop()

        wav = self._recorder.stop()
        duration = time.time() - self._start_time

        if not wav:
            return  # silence / too short

        # --- Transcription ---
        try:
            raw = self._transcriber.transcribe(wav)
        except Exception as e:
            if self.on_error:
                self.on_error(str(e))
            return

        # Discard Whisper hallucinations (common on silence or noise)
        if not raw.strip() or raw.strip().lower() in _WHISPER_HALLUCINATIONS:
            return

        # --- Enhancement ---
        mode = self._cfg["enhancement"]["mode"]
        try:
            final = self._enhancer.enhance(raw, mode) if mode != "raw" else raw
        except Exception as e:
            # Enhancement is optional — fall back to raw text on failure
            final = raw
            if self.on_error:
                self.on_error(f"Enhancement failed, using raw: {e}")

        # --- Output ---
        injected = False
        if self._cfg["output"]["auto_paste"]:
            injected = self._injector.inject(final)
            if not injected:
                # xdotool failed — clipboard is the fallback so text isn't lost
                self._injector.copy_to_clipboard(final)
        else:
            self._injector.copy_to_clipboard(final)

        if self._cfg["output"]["save_history"]:
            db.save(raw, final, mode, duration_s=duration, injected=injected)

        if self.on_result:
            self.on_result(raw, final, injected)
