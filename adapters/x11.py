"""X11 platform implementations using xdotool (text injection) and pynput (hotkeys).

X11Injector:
  Uses `xdotool type` to simulate keypresses in the focused window.
  Falls back to xclip (then xdotool set-selection) for clipboard operations.
  `--clearmodifiers` ensures Ctrl/Shift aren't still held when typing begins.

X11HotkeyListener:
  Uses pynput's keyboard.Listener for passive global key monitoring.
  IMPORTANT: pynput on X11 is a *passive* listener — it does NOT consume
  the keypress. The hotkey (e.g. Ctrl+Space) still reaches whatever app
  has focus. This causes a brief popup in apps that respond to Ctrl+Space
  (browsers, IDEs). Fixing this properly requires XGrabKey (exclusive grab)
  which is a significant rework and not yet implemented.

  Left/right modifier normalisation: pynput reports Key.ctrl_l and Key.ctrl_r
  separately from Key.ctrl. We normalise all variants to the canonical key
  so the user doesn't have to hold specifically the left or right modifier.
"""

import subprocess
import threading
from typing import Callable

from pynput import keyboard

from adapters.base import HotkeyListener, TextInjector

# Maps config modifier names → pynput canonical Key constants
_MOD_MAP = {
    "ctrl": keyboard.Key.ctrl,
    "alt": keyboard.Key.alt,
    "shift": keyboard.Key.shift,
    "super": keyboard.Key.cmd,
}


class X11Injector(TextInjector):
    def inject(self, text: str) -> bool:
        """Type text into the active X11 window using xdotool.
        --clearmodifiers releases any held keys (e.g. Ctrl from the hotkey)
        before typing begins, preventing accidental shortcuts.
        """
        try:
            subprocess.run(
                ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
                check=True,
                timeout=10,
            )
            return True
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return False

    def copy_to_clipboard(self, text: str) -> bool:
        """Put text on the X11 clipboard. Tries xclip first, falls back to xdotool."""
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode(),
                check=True,
                timeout=5,
            )
            return True
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            pass
        # xclip not installed — try xdotool as fallback
        try:
            subprocess.run(
                ["xdotool", "set-selection", "--", text],
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


class X11HotkeyListener(HotkeyListener):
    def __init__(self, modifiers: list[str], key: str):
        # Set of canonical pynput Key objects that must all be held simultaneously
        self._required_mods = {_MOD_MAP[m] for m in modifiers if m in _MOD_MAP}
        self._key = self._parse_key(key)
        self._held_mods: set = set()
        self._hotkey_active = False
        self._listener = None
        self._on_press: Callable | None = None
        self._on_release: Callable | None = None
        self._lock = threading.Lock()

    def _parse_key(self, key: str):
        """Convert a config key string to a pynput Key or KeyCode.
        Single characters → KeyCode.from_char; named keys (e.g. "space") → Key enum.
        """
        if len(key) == 1:
            return keyboard.KeyCode.from_char(key)
        try:
            return getattr(keyboard.Key, key)
        except AttributeError:
            return keyboard.KeyCode.from_char(key)

    def _normalize_mod(self, key):
        """Map Key.ctrl_l / Key.ctrl_r → Key.ctrl (and similar for alt/shift/super).
        pynput fires left/right variants, but the config stores canonical names.
        """
        for canonical in self._required_mods:
            name = canonical.name.rstrip("_lr") if hasattr(canonical, "name") else None
            if (
                name
                and hasattr(keyboard.Key, f"{name}_l")
                and (
                    key == getattr(keyboard.Key, f"{name}_l")
                    or key == getattr(keyboard.Key, f"{name}_r")
                )
            ):
                return canonical
        return key

    def _on_key_press(self, key):
        """Track held modifiers; fire on_press when the full combo is active."""
        norm = self._normalize_mod(key)
        if norm in self._required_mods:
            with self._lock:
                self._held_mods.add(norm)
        elif self._held_mods == self._required_mods and self._keys_match(
            key, self._key
        ):
            if not self._hotkey_active:
                self._hotkey_active = True
                if self._on_press:
                    # Run in a separate thread so the pynput listener isn't blocked
                    threading.Thread(target=self._on_press, daemon=True).start()

    def _on_key_release(self, key):
        """Track modifier releases; fire on_release when the trigger key is released."""
        norm = self._normalize_mod(key)
        if norm in self._required_mods:
            with self._lock:
                self._held_mods.discard(norm)
        if self._keys_match(key, self._key) and self._hotkey_active:
            self._hotkey_active = False
            if self._on_release:
                threading.Thread(target=self._on_release, daemon=True).start()

    def _keys_match(self, a, b) -> bool:
        """Compare two pynput key objects, handling KeyCode.char equality."""
        if a == b:
            return True
        if hasattr(a, "char") and hasattr(b, "char"):
            return a.char == b.char
        return False

    def start(self, on_press: Callable, on_release: Callable) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
