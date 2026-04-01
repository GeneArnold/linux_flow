"""linux_flow GTK4 Application."""

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
        # Build window (hidden by default)
        self._window = MainWindow(app, self._engine)

        # Wire overlay to engine
        self._engine.on_audio_level = self._overlay.push_level
        self._engine.on_recording_start = self._on_recording_start
        self._engine.on_recording_stop = self._on_recording_stop

        # Build tray
        self._tray = Tray(
            engine=self._engine,
            open_window_cb=self._show_window,
            quit_cb=self._quit,
        )
        self._tray.build()

        # Start engine (hotkey listener)
        try:
            self._engine.start()
        except Exception as e:
            print(f"Engine failed to start: {e}")

        # Show window on first launch
        self._show_window()

    def _show_window(self) -> None:
        if self._window:
            self._window.present()

    def _on_recording_start(self) -> None:
        self._overlay.show()
        if self._tray:
            self._tray.set_recording(True)

    def _on_recording_stop(self) -> None:
        self._overlay.hide()
        if self._tray:
            self._tray.set_recording(False)

    def _quit(self) -> None:
        self._engine.stop()
        if self._tray:
            self._tray.stop()
        self.quit()
