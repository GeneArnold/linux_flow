"""Tray icon manager — spawns tray_process.py as a subprocess.

WHY a subprocess?
    pystray uses AppIndicator3 on Linux, which requires GTK3. Our main app
    uses GTK4. Loading both GTK versions in the same process causes a crash.
    The subprocess isolates GTK3 completely — it runs tray_process.py which
    has no GTK4 imports at all.

IPC protocol (newline-delimited JSON):
    Parent → child (via stdin):
        {"cmd": "set_recording", "value": true/false}
        {"cmd": "quit"}

    Child → parent (via stdout):
        {"event": "copy_last"}
        {"event": "open_settings"}
        {"event": "quit"}

The reader thread (_read_events) runs as a daemon and dispatches incoming
events back onto the GTK main loop via GLib.idle_add.
"""

import json
import subprocess
import threading
from pathlib import Path

from gi.repository import GLib

_TRAY_SCRIPT = Path(__file__).parent / "tray_process.py"
# Use the venv Python explicitly so tray_process.py gets the same packages
_PYTHON = Path(__file__).parent.parent / "venv" / "bin" / "python"


class Tray:
    def __init__(self, engine, open_window_cb, quit_cb):
        self._engine = engine
        self._open_window_cb = open_window_cb
        self._quit_cb = quit_cb
        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None

    def build(self) -> None:
        """Launch the tray subprocess and start the event reader thread."""
        self._proc = subprocess.Popen(
            [str(_PYTHON), str(_TRAY_SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered so JSON arrives promptly
        )
        self._reader_thread = threading.Thread(target=self._read_events, daemon=True)
        self._reader_thread.start()

    def set_recording(self, recording: bool) -> None:
        """Tell the tray process to update its icon and tooltip."""
        self._send({"cmd": "set_recording", "value": recording})

    def stop(self) -> None:
        """Cleanly shut down the tray subprocess."""
        self._send({"cmd": "quit"})
        if self._proc:
            self._proc.wait(timeout=2)

    def _send(self, msg: dict) -> None:
        """Write a JSON message to the subprocess stdin. Silently ignores pipe errors."""
        if self._proc and self._proc.stdin:
            try:
                self._proc.stdin.write(json.dumps(msg) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass  # subprocess already exited

    def _read_events(self) -> None:
        """Read JSON events from subprocess stdout and dispatch to the GTK main loop.
        Runs on a daemon thread — exits automatically when the subprocess closes.
        """
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
                # This runs on the reader thread — engine.copy_last_transcript()
                # is thread-safe (SQLite + injector both handle concurrency)
                text = self._engine.copy_last_transcript()
                if not text:
                    print("No transcript history yet.")
            elif event == "open_settings":
                GLib.idle_add(self._open_window_cb)
            elif event == "quit":
                GLib.idle_add(self._quit_cb)
