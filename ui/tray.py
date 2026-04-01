"""Tray icon manager — spawns tray_process.py as a subprocess.

This keeps GTK3 (pystray/AppIndicator) completely isolated from our GTK4 app.
Communication is via newline-delimited JSON over stdin/stdout.
"""

import json
import subprocess
import sys
import threading
from pathlib import Path

from gi.repository import GLib

_TRAY_SCRIPT = Path(__file__).parent / "tray_process.py"
_PYTHON = Path(__file__).parent.parent / "venv" / "bin" / "python"


class Tray:
    def __init__(self, engine, open_window_cb, quit_cb):
        self._engine = engine
        self._open_window_cb = open_window_cb
        self._quit_cb = quit_cb
        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None

    def build(self) -> None:
        self._proc = subprocess.Popen(
            [str(_PYTHON), str(_TRAY_SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader_thread = threading.Thread(target=self._read_events, daemon=True)
        self._reader_thread.start()

    def set_recording(self, recording: bool) -> None:
        self._send({"cmd": "set_recording", "value": recording})

    def stop(self) -> None:
        self._send({"cmd": "quit"})
        if self._proc:
            self._proc.wait(timeout=2)

    def _send(self, msg: dict) -> None:
        if self._proc and self._proc.stdin:
            try:
                self._proc.stdin.write(json.dumps(msg) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    def _read_events(self) -> None:
        if not self._proc or not self._proc.stdout:
            return
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = msg.get("event")
            if event == "copy_last":
                text = self._engine.copy_last_transcript()
                if not text:
                    print("No transcript history yet.")
            elif event == "open_settings":
                GLib.idle_add(self._open_window_cb)
            elif event == "quit":
                GLib.idle_add(self._quit_cb)
