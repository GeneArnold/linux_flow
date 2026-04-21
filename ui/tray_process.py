#!/usr/bin/env python3
"""Standalone tray icon process.

Runs as a subprocess of the main GTK4 app so that pystray/GTK3 and our
GTK4 window never share the same process. Communicates via stdin/stdout
as newline-delimited JSON.

Commands from parent  → stdin:   {"cmd": "set_recording", "value": true/false}
                                  {"cmd": "set_processing", "value": true/false}
                                  {"cmd": "quit"}
Events to parent      → stdout:  {"event": "copy_last"}
                                  {"event": "open_settings"}
                                  {"event": "quit"}
"""

import json
import sys
import threading

import pystray
from PIL import Image, ImageDraw


def _make_mic_icon(recording: bool = False) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (220, 50, 50, 255) if recording else (210, 210, 210, 255)

    # Capsule body
    d.rounded_rectangle([22, 4, 42, 36], radius=10, fill=color)

    # Pickup arc — bottom half curves under the capsule like a stand mic
    d.arc([12, 18, 52, 50], start=0, end=180, fill=color, width=4)

    # Neck
    d.rectangle([30, 50, 34, 57], fill=color)

    # Base
    d.rounded_rectangle([19, 57, 45, 62], radius=3, fill=color)

    return img


def _make_star_icon() -> Image.Image:
    import math

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (210, 210, 210, 255)

    cx, cy, outer, inner = 32, 32, 28, 11
    points = []
    for i in range(10):
        r = outer if i % 2 == 0 else inner
        angle = math.radians(-90 + i * 36)
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    d.polygon(points, fill=color)

    return img


def _send(event: dict) -> None:
    print(json.dumps(event), flush=True)


def _on_copy_last(icon, item) -> None:
    _send({"event": "copy_last"})


def _on_settings(icon, item) -> None:
    _send({"event": "open_settings"})


def _on_quit(icon, item) -> None:
    _send({"event": "quit"})
    icon.stop()


def _read_commands(icon) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        cmd = msg.get("cmd")
        if cmd == "set_recording":
            icon.icon = _make_mic_icon(msg.get("value", False))
            icon.title = (
                "Linux Flow — Recording..." if msg.get("value") else "Linux Flow"
            )
        elif cmd == "set_processing":
            if msg.get("value", False):
                icon.icon = _make_star_icon()
                icon.title = "Linux Flow — Processing..."
            else:
                icon.icon = _make_mic_icon(False)
                icon.title = "Linux Flow"
        elif cmd == "quit":
            icon.stop()
            return
    # stdin closed — parent process is gone, shut down
    icon.stop()


def main() -> None:
    menu = pystray.Menu(
        pystray.MenuItem("Linux Flow", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Copy Last Transcript", _on_copy_last),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Settings...", _on_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _on_quit),
    )
    icon = pystray.Icon(
        name="linux-flow",
        icon=_make_mic_icon(False),
        title="Linux Flow",
        menu=menu,
    )

    # Start command reader thread
    t = threading.Thread(target=_read_commands, args=(icon,), daemon=True)
    t.start()

    icon.run()


if __name__ == "__main__":
    main()
