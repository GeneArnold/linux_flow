"""Wayland platform stubs — ready for future implementation.

When this machine switches back to Wayland, implement:
  - WaylandInjector.inject()   → wl-copy + ydotool key ctrl+v
  - WaylandInjector.copy_to_clipboard() → wl-copy
  - WaylandHotkeyListener     → python-evdev reading /dev/input/eventX
                                  (user must be in 'input' group)

Required packages for Wayland:
  apt: wl-clipboard ydotool
  pip: evdev
  groups: sudo usermod -aG input,uinput $USER
"""

from typing import Callable

from adapters.base import HotkeyListener, TextInjector


class WaylandInjector(TextInjector):
    def inject(self, text: str) -> bool:
        raise NotImplementedError(
            "Wayland text injection not yet implemented. "
            "Switch to X11 or implement via wl-copy + ydotool."
        )

    def copy_to_clipboard(self, text: str) -> bool:
        import subprocess

        try:
            subprocess.run(
                ["wl-copy", "--", text],
                check=True,
                timeout=5,
            )
            return True
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return False


class WaylandHotkeyListener(HotkeyListener):
    def __init__(self, modifiers: list[str], key: str):
        self._modifiers = modifiers
        self._key = key

    def start(self, on_press: Callable, on_release: Callable) -> None:
        raise NotImplementedError(
            "Wayland global hotkeys not yet implemented. "
            "Implement via python-evdev reading /dev/input/eventX."
        )

    def stop(self) -> None:
        pass
