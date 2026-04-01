"""Abstract interfaces for platform-specific text injection and hotkey listening.

Concrete implementations:
  X11     → adapters/x11.py      (current — uses xdotool + pynput)
  Wayland → adapters/wayland.py  (stubs — not yet implemented)

The factory functions below auto-detect the session type from XDG_SESSION_TYPE
and return the appropriate implementation. Engine and UI code only ever touch
these ABCs and the factory functions, never the concrete classes directly.

Adding a new platform:
1. Create adapters/<platform>.py implementing TextInjector and HotkeyListener
2. Add a branch to get_injector() and get_hotkey_listener() below
"""

import os
from abc import ABC, abstractmethod
from typing import Callable


class TextInjector(ABC):
    """Types text into the currently focused window and/or sets the clipboard."""

    @abstractmethod
    def inject(self, text: str) -> bool:
        """Type text into the active window. Returns True on success."""

    @abstractmethod
    def copy_to_clipboard(self, text: str) -> bool:
        """Place text on the system clipboard. Returns True on success."""


class HotkeyListener(ABC):
    """Listens globally for a configurable hotkey combination."""

    @abstractmethod
    def start(self, on_press: Callable, on_release: Callable) -> None:
        """Start the listener. Callbacks are fired from a background thread —
        callers must use GLib.idle_add() for any GTK operations."""

    @abstractmethod
    def stop(self) -> None:
        """Stop listening and release any held resources."""


def get_session_type() -> str:
    """Return 'x11' or 'wayland' based on XDG_SESSION_TYPE env var."""
    return os.environ.get("XDG_SESSION_TYPE", "x11").lower()


def get_injector() -> TextInjector:
    """Return the TextInjector for the current display session."""
    if get_session_type() == "wayland":
        from adapters.wayland import WaylandInjector

        return WaylandInjector()
    from adapters.x11 import X11Injector

    return X11Injector()


def get_hotkey_listener(modifiers: list[str], key: str) -> HotkeyListener:
    """Return the HotkeyListener for the current display session."""
    if get_session_type() == "wayland":
        from adapters.wayland import WaylandHotkeyListener

        return WaylandHotkeyListener(modifiers, key)
    from adapters.x11 import X11HotkeyListener

    return X11HotkeyListener(modifiers, key)
