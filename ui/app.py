"""Linux Flow GTK4 Application entry point.

LinuxFlowApp is the Adw.Application subclass. It owns the top-level objects
(engine, window, overlay, tray) and wires them together on activation.

Startup sequence:
    1. App activates → _on_activate()
    2. MainWindow built (hidden until shown)
    3. Overlay created (hidden until recording)
    4. Tray subprocess spawned
    5. Engine started (hotkey listener goes live)
    6. Settings window shown on first launch

The window hides (not destroys) on close so the app keeps running in the tray.
To truly quit, the user selects Quit from the tray menu.
"""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from core.engine import Engine
from ui.overlay import Overlay
from ui.tray import Tray
from ui.window import MainWindow


class LinuxFlowApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.genearnold.linux_flow",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._engine = Engine()
        self._window: MainWindow | None = None
        self._tray: Tray | None = None
        self._overlay = Overlay()

        self.connect("activate", self._on_activate)

    def _on_activate(self, app) -> None:
        # Build window (hidden by default — shown below on first launch)
        self._window = MainWindow(app, self._engine)

        # Wire engine callbacks to overlay and tray
        self._engine.on_audio_level = self._overlay.push_level
        self._engine.on_recording_start = self._on_recording_start
        self._engine.on_recording_stop = self._on_recording_stop

        # Tray runs as a subprocess to avoid the GTK3/GTK4 conflict
        self._tray = Tray(
            engine=self._engine,
            open_window_cb=self._show_window,
            quit_cb=self._quit,
        )
        self._tray.build()

        # Start engine — hotkey listener goes live here
        try:
            self._engine.start()
        except Exception as e:
            print(f"Engine failed to start: {e}", file=sys.stderr)

        # Show settings window on first launch so the user can configure the API key
        self._show_window()

    def _show_window(self) -> None:
        """Bring the settings window to the front (creates it if needed)."""
        if self._window:
            self._window.present()

    def _on_recording_start(self) -> None:
        """Hotkey pressed — show overlay and update tray icon."""
        self._overlay.show()
        if self._tray:
            self._tray.set_recording(True)

    def _on_recording_stop(self) -> None:
        """Hotkey released — hide overlay and reset tray icon."""
        self._overlay.hide()
        if self._tray:
            self._tray.set_recording(False)

    def _quit(self) -> None:
        """Clean shutdown: stop engine, kill tray subprocess, quit GTK loop."""
        self._engine.stop()
        if self._tray:
            self._tray.stop()
        self.quit()
