"""Advanced settings page."""

import os
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

import config

_AUTOSTART_FILE = Path.home() / ".config" / "autostart" / "linux-flow.desktop"
_APP_DIR = Path(__file__).parent.parent.parent


def _write_autostart() -> None:
    _AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
    venv_python = _APP_DIR / "venv" / "bin" / "python"
    main_py = _APP_DIR / "main.py"
    _AUTOSTART_FILE.write_text(f"""[Desktop Entry]
Type=Application
Name=Linux Flow
Comment=Voice dictation for Linux
Exec={venv_python} {main_py}
Icon=audio-input-microphone
StartupNotify=false
X-GNOME-Autostart-enabled=true
""")


def _remove_autostart() -> None:
    if _AUTOSTART_FILE.exists():
        _AUTOSTART_FILE.unlink()


class AdvancedPage(Gtk.Box):
    def __init__(self, engine):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._engine = engine
        self._cfg = config.load()

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        outer.set_margin_top(24)
        outer.set_margin_bottom(24)
        outer.set_margin_start(24)
        outer.set_margin_end(24)
        scroll.set_child(outer)

        # --- Startup group ---
        startup_group = Adw.PreferencesGroup(title="Startup")
        outer.append(startup_group)

        autostart_row = Adw.SwitchRow(
            title="Launch on Login",
            subtitle="Start Linux Flow automatically when you log in",
        )
        autostart_row.set_active(_AUTOSTART_FILE.exists())
        autostart_row.connect("notify::active", self._on_autostart_changed)
        startup_group.add(autostart_row)

        # --- Overlay group ---
        overlay_group = Adw.PreferencesGroup(
            title="Recording Indicator",
            description="The waveform overlay that appears while recording",
        )
        outer.append(overlay_group)

        pos_row = Adw.ActionRow(title="Overlay Position")
        self._pos_combo = Gtk.DropDown.new_from_strings(["Bottom", "Top"])
        self._pos_combo.set_valign(Gtk.Align.CENTER)
        current_pos = self._cfg.get("ui", {}).get("overlay_position", "bottom")
        self._pos_combo.set_selected(0 if current_pos == "bottom" else 1)
        self._pos_combo.connect("notify::selected", self._on_pos_changed)
        pos_row.add_suffix(self._pos_combo)
        overlay_group.add(pos_row)

        # --- Compatibility group (only shown if IBus is installed) ---
        if self._ibus_schema_exists():
            compat_group = Adw.PreferencesGroup(
                title="Compatibility",
                description="Known conflicts with other system components",
            )
            outer.append(compat_group)

            ibus_row = Adw.ActionRow(
                title="IBus Input Method Conflict",
                subtitle=(
                    "Ctrl+Space is also used by IBus (Ubuntu's input method switcher), "
                    "causing a brief popup when you trigger Linux Flow. "
                    "Click Fix to disable the IBus hotkey — this does not affect typing."
                ),
            )
            ibus_row.set_subtitle_lines(4)

            ibus_status = self._ibus_status_label()
            ibus_row.add_suffix(ibus_status)

            fix_btn = Gtk.Button(label="Fix")
            fix_btn.set_valign(Gtk.Align.CENTER)
            fix_btn.add_css_class("suggested-action")
            fix_btn.connect("clicked", lambda _, lbl=ibus_status: self._on_fix_ibus(lbl))
            ibus_row.add_suffix(fix_btn)

            reset_btn = Gtk.Button(label="Reset")
            reset_btn.set_valign(Gtk.Align.CENTER)
            reset_btn.add_css_class("flat")
            reset_btn.set_tooltip_text("Restore IBus default hotkey")
            reset_btn.connect(
                "clicked", lambda _, lbl=ibus_status: self._on_reset_ibus(lbl)
            )
            ibus_row.add_suffix(reset_btn)

            compat_group.add(ibus_row)

        # --- Debug group ---
        debug_group = Adw.PreferencesGroup(title="Diagnostics")
        outer.append(debug_group)

        config_row = Adw.ActionRow(
            title="Config File",
            subtitle=str(_APP_DIR / "linux_flow.toml"),
        )
        open_config_btn = Gtk.Button(label="Open")
        open_config_btn.set_valign(Gtk.Align.CENTER)
        open_config_btn.add_css_class("flat")
        open_config_btn.connect("clicked", self._on_open_config)
        config_row.add_suffix(open_config_btn)
        debug_group.add(config_row)

        db_row = Adw.ActionRow(
            title="History Database",
            subtitle=str(_APP_DIR / "history.db"),
        )
        debug_group.add(db_row)

    def _ibus_schema_exists(self) -> bool:
        """Check if the IBus gsettings schema is installed on this system."""
        try:
            result = subprocess.run(
                ["gsettings", "list-keys", "org.freedesktop.ibus.general.hotkey"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _ibus_status_label(self) -> Gtk.Label:
        lbl = Gtk.Label()
        lbl.set_valign(Gtk.Align.CENTER)
        self._refresh_ibus_label(lbl)
        return lbl

    def _refresh_ibus_label(self, lbl: Gtk.Label) -> None:
        result = subprocess.run(
            ["gsettings", "get", "org.freedesktop.ibus.general.hotkey", "triggers"],
            capture_output=True,
            text=True,
        )
        value = result.stdout.strip()
        if value == "@as []" or value == "[]":
            lbl.set_text("Fixed")
            lbl.add_css_class("success")
            lbl.remove_css_class("warning")
        else:
            lbl.set_text("Conflicting")
            lbl.add_css_class("warning")
            lbl.remove_css_class("success")

    def _on_fix_ibus(self, lbl: Gtk.Label) -> None:
        subprocess.run(
            [
                "gsettings",
                "set",
                "org.freedesktop.ibus.general.hotkey",
                "triggers",
                "[]",
            ],
            check=True,
        )
        self._refresh_ibus_label(lbl)

    def _on_reset_ibus(self, lbl: Gtk.Label) -> None:
        subprocess.run(
            ["gsettings", "reset", "org.freedesktop.ibus.general.hotkey", "triggers"]
        )
        self._refresh_ibus_label(lbl)

    def _on_pos_changed(self, combo, _) -> None:
        pos = "bottom" if combo.get_selected() == 0 else "top"
        config.set_value("ui", "overlay_position", pos)

    def _on_autostart_changed(self, row, _) -> None:
        if row.get_active():
            _write_autostart()
        else:
            _remove_autostart()
        config.set_value("app", "autostart", row.get_active())

    def _on_open_config(self, _) -> None:
        config_path = _APP_DIR / "linux_flow.toml"
        subprocess.Popen(["xdg-open", str(config_path)])
