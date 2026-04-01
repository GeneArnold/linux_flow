"""General settings page."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk

import config
from core.recorder import Recorder

_MODES = ["raw", "clean", "rewrite"]
_MODE_LABELS = ["Raw (no AI)", "Clean (fix grammar)", "Rewrite (polish prose)"]

_GDK_MOD_MAP = {
    "Control_L": "ctrl",
    "Control_R": "ctrl",
    "Alt_L": "alt",
    "Alt_R": "alt",
    "Shift_L": "shift",
    "Shift_R": "shift",
    "Super_L": "super",
    "Super_R": "super",
}


class _HotkeyCaptureButton(Gtk.Button):
    """Button that records a hotkey combo when clicked."""

    def __init__(self, modifiers: list[str], key: str, on_change):
        super().__init__()
        self._modifiers = list(modifiers)
        self._key = key
        self._on_change = on_change
        self._capturing = False
        self._held_mods: set[str] = set()
        self._pending_mods: list[str] = []
        self._pending_key: str | None = None

        self.add_css_class("monospace")
        self.set_valign(Gtk.Align.CENTER)
        self._refresh_label()

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        key_ctrl.connect("key-released", self._on_key_released)
        self.add_controller(key_ctrl)
        self.connect("clicked", self._start_capture)

    def _refresh_label(self) -> None:
        parts = self._modifiers + [self._key]
        self.set_label("+".join(parts))

    def _start_capture(self, *_) -> None:
        if self._capturing:
            return
        self._capturing = True
        self._held_mods.clear()
        self._pending_mods = []
        self._pending_key = None
        self.set_label("Press shortcut…")
        self.add_css_class("suggested-action")
        self.grab_focus()

    def _cancel_capture(self) -> None:
        self._capturing = False
        self._held_mods.clear()
        self.remove_css_class("suggested-action")
        self._refresh_label()

    def _on_key_pressed(self, _ctrl, keyval, _code, _state) -> bool:
        if not self._capturing:
            return False
        name = Gdk.keyval_name(keyval) or ""
        if name == "Escape":
            self._cancel_capture()
            return True
        if name in _GDK_MOD_MAP:
            self._held_mods.add(_GDK_MOD_MAP[name])
            return True
        # Non-modifier — record it
        key = "space" if name == "space" else name.lower()
        self._pending_mods = sorted(self._held_mods)
        self._pending_key = key
        return True

    def _on_key_released(self, _ctrl, keyval, _code, _state) -> bool:
        if not self._capturing:
            return False
        name = Gdk.keyval_name(keyval) or ""
        if name in _GDK_MOD_MAP:
            self._held_mods.discard(_GDK_MOD_MAP[name])
            return True
        # Main key released — finalise
        if self._pending_key:
            self._capturing = False
            self._modifiers = self._pending_mods
            self._key = self._pending_key
            self.remove_css_class("suggested-action")
            self._refresh_label()
            self._on_change(self._modifiers, self._key)
        return True


class GeneralPage(Gtk.Box):
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

        # --- Hotkey group ---
        hotkey_group = Adw.PreferencesGroup(title="Shortcut")
        outer.append(hotkey_group)

        hotkey_row = Adw.ActionRow(
            title="Transcription Shortcut",
            subtitle="Click to change — then press your new combo",
        )
        capture_btn = _HotkeyCaptureButton(
            self._cfg["hotkey"]["modifiers"],
            self._cfg["hotkey"]["key"],
            self._on_hotkey_changed,
        )
        hotkey_row.add_suffix(capture_btn)
        hotkey_group.add(hotkey_row)

        # --- Audio group ---
        audio_group = Adw.PreferencesGroup(title="Audio")
        outer.append(audio_group)

        mic_row = Adw.ActionRow(title="Microphone")
        self._mic_combo = Gtk.DropDown()
        self._mic_combo.set_valign(Gtk.Align.CENTER)
        self._populate_mics()
        self._mic_combo.connect("notify::selected", self._on_mic_changed)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_valign(Gtk.Align.CENTER)
        refresh_btn.add_css_class("flat")
        refresh_btn.set_tooltip_text("Refresh microphone list")
        refresh_btn.connect("clicked", lambda _: self._populate_mics())

        mic_row.add_suffix(self._mic_combo)
        mic_row.add_suffix(refresh_btn)
        audio_group.add(mic_row)

        # --- Enhancement group ---
        enhance_group = Adw.PreferencesGroup(title="AI Enhancement")
        outer.append(enhance_group)

        mode_row = Adw.ActionRow(title="Mode")
        self._mode_combo = Gtk.DropDown.new_from_strings(_MODE_LABELS)
        self._mode_combo.set_valign(Gtk.Align.CENTER)
        current_mode = self._cfg["enhancement"]["mode"]
        self._mode_combo.set_selected(
            _MODES.index(current_mode) if current_mode in _MODES else 1
        )
        self._mode_combo.connect("notify::selected", self._on_mode_changed)
        mode_row.add_suffix(self._mode_combo)
        enhance_group.add(mode_row)

        # --- Output group ---
        output_group = Adw.PreferencesGroup(title="Output")
        outer.append(output_group)

        paste_row = Adw.SwitchRow(
            title="Auto-paste into active window",
            subtitle="Uses xdotool to type text at cursor position",
        )
        paste_row.set_active(self._cfg["output"]["auto_paste"])
        paste_row.connect("notify::active", self._on_paste_changed)
        output_group.add(paste_row)

        history_row = Adw.SwitchRow(
            title="Save to history",
            subtitle="Keep a local log of all transcriptions",
        )
        history_row.set_active(self._cfg["output"]["save_history"])
        history_row.connect("notify::active", self._on_history_changed)
        output_group.add(history_row)

    def _on_hotkey_changed(self, modifiers: list[str], key: str) -> None:
        config.set_value("hotkey", "modifiers", modifiers)
        config.set_value("hotkey", "key", key)
        self._engine.reload()

    def _populate_mics(self, *_) -> None:
        devices = Recorder.list_devices()
        self._mic_devices = devices
        strings = Gtk.StringList()
        current = self._cfg["audio"]["device_index"]
        selected = 0
        for i, dev in enumerate(devices):
            strings.append(dev["name"])
            if dev["index"] == current:
                selected = i
        self._mic_combo.set_model(strings)
        self._mic_combo.set_selected(selected)

    def _on_mic_changed(self, combo, _) -> None:
        idx = combo.get_selected()
        if hasattr(self, "_mic_devices") and idx < len(self._mic_devices):
            dev_index = self._mic_devices[idx]["index"]
            config.set_value("audio", "device_index", dev_index)
            self._engine.reload()

    def _on_mode_changed(self, combo, _) -> None:
        mode = _MODES[combo.get_selected()]
        config.set_value("enhancement", "mode", mode)
        self._engine.reload()

    def _on_paste_changed(self, row, _) -> None:
        config.set_value("output", "auto_paste", row.get_active())
        self._engine.reload()

    def _on_history_changed(self, row, _) -> None:
        config.set_value("output", "save_history", row.get_active())
        self._engine.reload()
