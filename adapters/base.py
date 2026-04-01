"""Abstract interfaces for platform-specific operations.

X11 implementation:     adapters/x11.py
Wayland implementation: adapters/wayland.py (future)

Auto-detected at runtime via XDG_SESSION_TYPE environment variable.
"""

import os
from abc import ABC, abstractmethod
from typing import Callable


class TextInjector(ABC):
    """Injects text into the currently focused window."""

    @abstractmethod
    def inject(self, text: str) -> bool:
        """Type text into the active window. Returns True on success."""

    @abstractmethod
    def copy_to_clipboard(self, text: str) -> bool:
        """Place text on the system clipboard. Returns True on success."""


class HotkeyListener(ABC):
    """Listens for a global hotkey combination."""

    @abstractmethod
    def start(self, on_press: Callable, on_release: Callable) -> None:
        """Start listening. on_press/on_release called when hotkey state changes."""

    @abstractmethod
    def stop(self) -> None:
        """Stop listening and clean up."""


def get_session_type() -> str:
    """Return 'x11' or 'wayland' based on the current session."""
    return os.environ.get("XDG_SESSION_TYPE", "x11").lower()


def get_injector() -> TextInjector:
    session = get_session_type()
    if session == "wayland":
        from adapters.wayland import WaylandInjector

        return WaylandInjector()
    from adapters.x11 import X11Injector

    return X11Injector()


def get_hotkey_listener(modifiers: list[str], key: str) -> HotkeyListener:
    session = get_session_type()
    if session == "wayland":
        from adapters.wayland import WaylandHotkeyListener

        return WaylandHotkeyListener(modifiers, key)
    from adapters.x11 import X11HotkeyListener

    return X11HotkeyListener(modifiers, key)
