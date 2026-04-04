"""Floating recording indicator overlay.

Shows a waveform visualizer centered at the top or bottom of the screen
while linux_flow is actively recording.

On X11, positioning uses xdotool since GTK4 removed window.move().
On Wayland, the window is presented as a regular window (compositors
handle placement; gtk4-layer-shell can be used for precise control).
"""

import math
import os
import threading
from collections import deque

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

import config

_BAR_COUNT = 20
_OVERLAY_WIDTH = 280
_OVERLAY_HEIGHT = 64
_UPDATE_HZ = 30
_EDGE_MARGIN = 40

_OVERLAY_TITLE = "linux_flow_overlay"
_IS_WAYLAND = os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _xdotool_move(x: int, y: int) -> None:
    """Move overlay window using xdotool (X11 only)."""
    if _IS_WAYLAND:
        return
    import subprocess

    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", _OVERLAY_TITLE],
            capture_output=True,
            text=True,
        )
        wid = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        if wid:
            subprocess.run(
                ["xdotool", "windowmove", wid, str(x), str(y)], capture_output=True
            )
    except Exception:
        pass


class Overlay:
    def __init__(self):
        self._window: Gtk.Window | None = None
        self._drawing_area: Gtk.DrawingArea | None = None
        self._levels: deque[float] = deque([0.0] * _BAR_COUNT, maxlen=_BAR_COUNT)
        self._running = False
        self._timer_id: int | None = None
        self._lock = threading.Lock()

    def show(self) -> None:
        GLib.idle_add(self._create_window)

    def hide(self) -> None:
        GLib.idle_add(self._destroy_window)

    def push_level(self, rms: float) -> None:
        with self._lock:
            self._levels.append(rms)

    def _get_position(self) -> str:
        try:
            return config.load().get("ui", {}).get("overlay_position", "bottom")
        except Exception:
            return "bottom"

    def _compute_xy(self, position: str) -> tuple[int, int]:
        display = Gdk.Display.get_default()
        monitor = display.get_monitors().get_item(0)
        geom = monitor.get_geometry()
        x = geom.x + (geom.width - _OVERLAY_WIDTH) // 2
        y = (
            geom.y + _EDGE_MARGIN
            if position == "top"
            else geom.y + geom.height - _OVERLAY_HEIGHT - _EDGE_MARGIN
        )
        return x, y

    def _create_window(self) -> bool:
        if self._window:
            return GLib.SOURCE_REMOVE

        position = self._get_position()
        x, y = self._compute_xy(position)

        win = Gtk.Window()
        win.set_decorated(False)
        win.set_resizable(False)
        win.set_default_size(_OVERLAY_WIDTH, _OVERLAY_HEIGHT)
        win.set_title(_OVERLAY_TITLE)

        if _IS_WAYLAND:
            # On Wayland, present as a normal undecorated window.
            # The compositor will handle placement.
            win.set_opacity(0.92)
        else:
            win.set_opacity(0.0)  # invisible until positioned by xdotool

        def _on_map(w):
            if _IS_WAYLAND:
                return
            def _move_then_show():
                _xdotool_move(x, y)
                w.set_opacity(0.92)
                return False
            GLib.timeout_add(80, _move_then_show)

        win.connect("map", _on_map)

        drawing = Gtk.DrawingArea()
        drawing.set_size_request(_OVERLAY_WIDTH, _OVERLAY_HEIGHT)
        drawing.set_draw_func(self._draw)
        win.set_child(drawing)
        win.present()

        self._window = win
        self._drawing_area = drawing
        self._running = True
        self._timer_id = GLib.timeout_add(1000 // _UPDATE_HZ, self._tick)

        return GLib.SOURCE_REMOVE

    def _destroy_window(self) -> bool:
        self._running = False
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        if self._window:
            self._window.close()
            self._window = None
            self._drawing_area = None
        with self._lock:
            self._levels = deque([0.0] * _BAR_COUNT, maxlen=_BAR_COUNT)
        return GLib.SOURCE_REMOVE

    def _tick(self) -> bool:
        if not self._running:
            return GLib.SOURCE_REMOVE
        if self._drawing_area:
            self._drawing_area.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _draw(self, area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        cr.set_source_rgba(0.08, 0.08, 0.10, 0.95)
        radius = height / 2
        cr.arc(radius, radius, radius, math.pi / 2, 3 * math.pi / 2)
        cr.arc(width - radius, radius, radius, -math.pi / 2, math.pi / 2)
        cr.close_path()
        cr.fill()

        # Red recording dot
        cr.set_source_rgba(0.95, 0.25, 0.25, 1.0)
        cr.arc(18, height // 2, 5, 0, 2 * math.pi)
        cr.fill()

        # Audio bars
        with self._lock:
            levels = list(self._levels)

        bar_area_x = 34
        bar_w = (width - bar_area_x - 14) / _BAR_COUNT
        gap = 2
        max_bar_h = height - 16

        for i, level in enumerate(levels):
            normalized = max(min(level / 3000.0, 1.0), 0.04)
            bar_h = max(4, int(normalized * max_bar_h))
            bx = bar_area_x + i * bar_w + gap / 2
            by = (height - bar_h) / 2
            r = min(1.0, normalized * 2)
            g = min(1.0, (1.0 - normalized) * 2)
            cr.set_source_rgba(r, g, 0.2, 0.9)
            cr.rectangle(bx, by, bar_w - gap, bar_h)
            cr.fill()
