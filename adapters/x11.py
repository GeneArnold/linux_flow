"""X11 platform implementations using pynput and xdotool."""

import subprocess
import threading
from typing import Callable

from pynput import keyboard

from adapters.base import HotkeyListener, TextInjector

_MOD_MAP = {
    "ctrl": keyboard.Key.ctrl,
    "alt": keyboard.Key.alt,
    "shift": keyboard.Key.shift,
    "super": keyboard.Key.cmd,
}


class X11Injector(TextInjector):
    def inject(self, text: str) -> bool:
        try:
            # xdotool type is the most reliable way to inject text on X11
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
        try:
            proc = subprocess.run(
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
        # fallback: xdotool set-selection
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
        self._required_mods = {_MOD_MAP[m] for m in modifiers if m in _MOD_MAP}
        self._key = self._parse_key(key)
        self._held_mods: set = set()
        self._hotkey_active = False
        self._listener = None
        self._on_press: Callable | None = None
        self._on_release: Callable | None = None
        self._lock = threading.Lock()

    def _parse_key(self, key: str):
        if len(key) == 1:
            return keyboard.KeyCode.from_char(key)
        try:
            return getattr(keyboard.Key, key)
        except AttributeError:
            return keyboard.KeyCode.from_char(key)

    def _is_modifier(self, key) -> bool:
        return key in self._required_mods or (
            hasattr(key, "name")
            and any(
                key == getattr(keyboard.Key, f"{name}_l", None)
                or key == getattr(keyboard.Key, f"{name}_r", None)
                for name in ["ctrl", "alt", "shift", "cmd"]
            )
        )

    def _normalize_mod(self, key):
        """Map left/right variants to the canonical modifier key."""
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
                    threading.Thread(target=self._on_press, daemon=True).start()

    def _on_key_release(self, key):
        norm = self._normalize_mod(key)
        if norm in self._required_mods:
            with self._lock:
                self._held_mods.discard(norm)
        if self._keys_match(key, self._key) and self._hotkey_active:
            self._hotkey_active = False
            if self._on_release:
                threading.Thread(target=self._on_release, daemon=True).start()

    def _keys_match(self, a, b) -> bool:
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
