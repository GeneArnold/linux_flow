"""Wayland platform implementations using evdev (hotkeys) and wtype/wl-copy (injection).

WaylandInjector:
  Uses `wtype` to simulate keypresses in the focused window.
  Uses `wl-copy` for clipboard operations.
  Falls back to clipboard-paste (wl-copy + wtype Ctrl+V) if direct typing fails.

WaylandHotkeyListener:
  Uses python-evdev to read keyboard events from /dev/input/eventX.
  The user must be in the 'input' group for read access to the device nodes.

Required packages:
  pacman: wl-clipboard wtype
  pip: evdev
  groups: sudo usermod -aG input $USER  (then log out/in)
"""

import os
import select
import subprocess
import threading
from typing import Callable

import evdev

from adapters.base import HotkeyListener, TextInjector

# ── Key name mapping: config names → evdev ecodes ──────────────────────
_MOD_ECODES = {
    "ctrl": {evdev.ecodes.KEY_LEFTCTRL, evdev.ecodes.KEY_RIGHTCTRL},
    "alt": {evdev.ecodes.KEY_LEFTALT, evdev.ecodes.KEY_RIGHTALT},
    "shift": {evdev.ecodes.KEY_LEFTSHIFT, evdev.ecodes.KEY_RIGHTSHIFT},
    "super": {evdev.ecodes.KEY_LEFTMETA, evdev.ecodes.KEY_RIGHTMETA},
}

# Single-char and named key → evdev ecode
_KEY_MAP = {
    "space": evdev.ecodes.KEY_SPACE,
    "enter": evdev.ecodes.KEY_ENTER,
    "return": evdev.ecodes.KEY_ENTER,
    "tab": evdev.ecodes.KEY_TAB,
    "escape": evdev.ecodes.KEY_ESC,
    "esc": evdev.ecodes.KEY_ESC,
    "backspace": evdev.ecodes.KEY_BACKSPACE,
    "delete": evdev.ecodes.KEY_DELETE,
    "up": evdev.ecodes.KEY_UP,
    "down": evdev.ecodes.KEY_DOWN,
    "left": evdev.ecodes.KEY_LEFT,
    "right": evdev.ecodes.KEY_RIGHT,
}

# Build a-z and 0-9 mappings
for _c in range(ord("a"), ord("z") + 1):
    _KEY_MAP[chr(_c)] = getattr(evdev.ecodes, f"KEY_{chr(_c).upper()}")
for _n in range(10):
    _KEY_MAP[str(_n)] = getattr(evdev.ecodes, f"KEY_{_n}")

# F1-F12
for _f in range(1, 13):
    _KEY_MAP[f"f{_f}"] = getattr(evdev.ecodes, f"KEY_F{_f}")


def _find_keyboards() -> list[evdev.InputDevice]:
    """Find all keyboard-like input devices the current user can read."""
    keyboards = []
    for path in sorted(evdev.list_devices()):
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            keys = caps.get(evdev.ecodes.EV_KEY, [])
            # A real keyboard has letter keys (KEY_A=30 through KEY_Z=53)
            has_letters = any(30 <= k <= 53 for k in keys)
            # Also check for space (57) as a fallback indicator
            has_space = evdev.ecodes.KEY_SPACE in keys
            if has_letters or (has_space and len(keys) > 20):
                keyboards.append(dev)
        except (PermissionError, OSError):
            continue
    return keyboards


class WaylandInjector(TextInjector):
    def inject(self, text: str) -> bool:
        """Type text into the active Wayland window using wtype."""
        try:
            subprocess.run(
                ["wtype", "--", text],
                check=True,
                timeout=10,
            )
            return True
        except FileNotFoundError:
            # wtype not installed — fall back to clipboard paste
            return self._clipboard_paste(text)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return self._clipboard_paste(text)

    def _clipboard_paste(self, text: str) -> bool:
        """Fall back to wl-copy + simulated Ctrl+V."""
        if not self.copy_to_clipboard(text):
            return False
        try:
            subprocess.run(
                ["wtype", "-M", "ctrl", "v", "-m", "ctrl"],
                check=True,
                timeout=5,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def copy_to_clipboard(self, text: str) -> bool:
        try:
            subprocess.run(
                ["wl-copy", "--", text],
                check=True,
                timeout=5,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False


class WaylandHotkeyListener(HotkeyListener):
    """Global hotkey listener using python-evdev on Wayland.

    Reads raw keyboard events from /dev/input/eventX. Requires the user
    to be in the 'input' group.
    """

    def __init__(self, modifiers: list[str], key: str):
        # Collect all evdev key codes that count as "modifier held"
        self._mod_codes: set[int] = set()
        for mod in modifiers:
            mod_lower = mod.lower()
            if mod_lower in _MOD_ECODES:
                self._mod_codes.update(_MOD_ECODES[mod_lower])

        # The trigger key ecode
        key_lower = key.lower()
        if key_lower not in _KEY_MAP:
            raise ValueError(
                f"Unknown key '{key}' for Wayland hotkey. "
                f"Supported: {', '.join(sorted(_KEY_MAP.keys()))}"
            )
        self._trigger_code = _KEY_MAP[key_lower]

        self._on_press: Callable | None = None
        self._on_release: Callable | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self, on_press: Callable, on_release: Callable) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._stop_event.clear()

        keyboards = _find_keyboards()
        if not keyboards:
            # Provide a helpful error message
            all_devices = evdev.list_devices()
            if not all_devices:
                raise RuntimeError(
                    "No input devices accessible. "
                    "Add your user to the 'input' group:\n"
                    "  sudo usermod -aG input $USER\n"
                    "Then log out and back in."
                )
            raise RuntimeError(
                f"Found {len(all_devices)} input device(s) but none are keyboards. "
                "Your keyboard may not be accessible. "
                "Ensure your user is in the 'input' group:\n"
                "  sudo usermod -aG input $USER\n"
                "Then log out and back in."
            )

        self._thread = threading.Thread(
            target=self._listen_loop,
            args=(keyboards,),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _listen_loop(self, keyboards: list[evdev.InputDevice]) -> None:
        """Poll all keyboard devices for key events."""
        held_mods: set[int] = set()
        hotkey_active = False

        # Build a fd → device map for select()
        fd_map = {dev.fd: dev for dev in keyboards}

        while not self._stop_event.is_set():
            # Use select with a timeout so we can check the stop event
            r, _, _ = select.select(fd_map.keys(), [], [], 0.1)
            for fd in r:
                dev = fd_map[fd]
                try:
                    for event in dev.read():
                        if event.type != evdev.ecodes.EV_KEY:
                            continue

                        key_event = evdev.categorize(event)
                        code = key_event.scancode

                        if key_event.keystate in (
                            evdev.events.KeyEvent.key_down,
                            evdev.events.KeyEvent.key_hold,
                        ):
                            # Track modifier state
                            if code in self._mod_codes:
                                held_mods.add(code)
                            elif code == self._trigger_code:
                                # Check if all required modifier groups are held
                                if self._mods_satisfied(held_mods) and not hotkey_active:
                                    hotkey_active = True
                                    if self._on_press:
                                        threading.Thread(
                                            target=self._on_press, daemon=True
                                        ).start()

                        elif key_event.keystate == evdev.events.KeyEvent.key_up:
                            if code in self._mod_codes:
                                held_mods.discard(code)
                            elif code == self._trigger_code and hotkey_active:
                                hotkey_active = False
                                if self._on_release:
                                    threading.Thread(
                                        target=self._on_release, daemon=True
                                    ).start()
                except (OSError, IOError):
                    # Device disconnected — remove from polling
                    del fd_map[fd]
                    if not fd_map:
                        return

        # Clean up
        for dev in fd_map.values():
            try:
                dev.close()
            except Exception:
                pass

    def _mods_satisfied(self, held: set[int]) -> bool:
        """Check that at least one key from each required modifier group is held."""
        for mod_name, codes in _MOD_ECODES.items():
            if codes & self._mod_codes:  # this modifier is required
                if not (codes & held):  # but none of its keys are held
                    return False
        return True
