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

import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib

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
        # GTK fires "activate" again every time the user re-launches the app
        # (e.g. clicks the dock icon while it's already running). Without this
        # guard we'd spawn a second tray subprocess and a second hotkey listener.
        if self._window is not None:
            self._show_window()
            return

        self._window = MainWindow(app, self._engine)

        # Wire engine callbacks to overlay and tray.
        # Window/pages may have already set on_result/on_error — wrap them
        # so both the existing handler and our tray updates run.
        self._engine.on_audio_level = self._overlay.push_level
        self._engine.on_recording_start = self._on_recording_start
        self._engine.on_recording_stop = self._on_recording_stop
        self._wrap_callback("on_result", self._on_result)
        self._wrap_callback("on_error", self._on_error)

        # Tray runs as a subprocess to avoid the GTK3/GTK4 conflict
        self._tray = Tray(
            engine=self._engine,
            open_window_cb=self._show_window,
            quit_cb=self._quit,
        )
        self._tray.build()

        # Ensure clean shutdown on SIGTERM/SIGINT (e.g. kill, Ctrl+C)
        for sig in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._quit)

        # Start engine — hotkey listener goes live here
        try:
            self._engine.start()
        except Exception as e:
            print(f"Engine failed to start: {e}", file=sys.stderr)

        # Show settings window on first launch so the user can configure the API key
        self._show_window()

    def _wrap_callback(self, attr: str, handler) -> None:
        """Chain handler onto an existing engine callback without replacing it."""
        existing = getattr(self._engine, attr, None)
        if existing:

            def chained(*args, **kwargs):
                existing(*args, **kwargs)
                handler(*args, **kwargs)

            setattr(self._engine, attr, chained)
        else:
            setattr(self._engine, attr, handler)

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
        """Hotkey released — hide overlay, show processing star in tray."""
        self._overlay.hide()
        if self._tray:
            self._tray.set_recording(False)
            self._tray.set_processing(True)

    def _on_result(self, raw: str, final: str, injected: bool) -> None:
        """Pipeline complete — return tray to idle mic icon."""
        if self._tray:
            self._tray.set_processing(False)

    def _on_error(self, message: str) -> None:
        """Pipeline failed — return tray to idle mic icon."""
        if self._tray:
            self._tray.set_processing(False)

    def _quit(self) -> bool:
        """Clean shutdown: stop engine, kill tray subprocess, quit GTK loop."""
        self._engine.stop()
        if self._tray:
            self._tray.stop()
        self.quit()
        return GLib.SOURCE_REMOVE
