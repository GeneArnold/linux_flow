"""Models settings page — Groq API key and model selection."""

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

import config

_WHISPER_MODELS = [
    "whisper-large-v3",
    "whisper-large-v3-turbo",
    "distil-whisper-large-v3-en",
]
_LLM_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
]


class ModelsPage(Gtk.Box):
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

        # --- API Key ---
        api_group = Adw.PreferencesGroup(
            title="Groq API",
            description="Get your free key at console.groq.com",
        )
        outer.append(api_group)

        key_row = Adw.PasswordEntryRow(title="API Key")
        key_row.set_text(self._cfg["groq"]["api_key"])
        key_row.connect("apply", self._on_key_apply)
        self._key_row = key_row

        save_btn = Gtk.Button(icon_name="document-save-symbolic")
        save_btn.set_valign(Gtk.Align.CENTER)
        save_btn.add_css_class("suggested-action")
        save_btn.set_tooltip_text("Save API key")
        save_btn.connect("clicked", lambda _: self._save_key())
        key_row.add_suffix(save_btn)

        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("leave", lambda _: self._save_key())
        key_row.add_controller(focus_ctrl)

        api_group.add(key_row)

        # Test connection row
        test_row = Adw.ActionRow(
            title="Verify Connection",
            subtitle="Check that your key works and both models are reachable",
        )
        self._test_btn = Gtk.Button(label="Test")
        self._test_btn.set_valign(Gtk.Align.CENTER)
        self._test_btn.add_css_class("pill")
        self._test_btn.connect("clicked", self._on_test_clicked)
        test_row.add_suffix(self._test_btn)

        self._result_label = Gtk.Label()
        self._result_label.set_valign(Gtk.Align.CENTER)
        self._result_label.set_visible(False)
        test_row.add_suffix(self._result_label)

        api_group.add(test_row)

        # --- Transcription model ---
        whisper_group = Adw.PreferencesGroup(
            title="Transcription Model",
            description="Whisper model used to convert speech to text",
        )
        outer.append(whisper_group)

        whisper_row = Adw.ActionRow(
            title="Whisper Model",
            subtitle="larger-v3 is most accurate; turbo is faster",
        )
        self._whisper_combo = Gtk.DropDown.new_from_strings(_WHISPER_MODELS)
        self._whisper_combo.set_valign(Gtk.Align.CENTER)
        current = self._cfg["groq"]["whisper_model"]
        if current in _WHISPER_MODELS:
            self._whisper_combo.set_selected(_WHISPER_MODELS.index(current))
        self._whisper_combo.connect("notify::selected", self._on_whisper_changed)
        whisper_row.add_suffix(self._whisper_combo)
        whisper_group.add(whisper_row)

        # --- Enhancement model ---
        llm_group = Adw.PreferencesGroup(
            title="Enhancement Model",
            description="LLM used to clean or rewrite transcriptions",
        )
        outer.append(llm_group)

        llm_row = Adw.ActionRow(
            title="LLM Model",
            subtitle="70b is highest quality; 8b is faster and cheaper",
        )
        self._llm_combo = Gtk.DropDown.new_from_strings(_LLM_MODELS)
        self._llm_combo.set_valign(Gtk.Align.CENTER)
        current_llm = self._cfg["groq"]["llm_model"]
        if current_llm in _LLM_MODELS:
            self._llm_combo.set_selected(_LLM_MODELS.index(current_llm))
        self._llm_combo.connect("notify::selected", self._on_llm_changed)
        llm_row.add_suffix(self._llm_combo)
        llm_group.add(llm_row)

    def _save_key(self) -> None:
        config.set_value("groq", "api_key", self._key_row.get_text())
        self._engine.reload()

    def _on_key_apply(self, row) -> None:
        self._save_key()

    def _on_test_clicked(self, _) -> None:
        self._test_btn.set_sensitive(False)
        self._test_btn.set_label("Testing…")
        self._result_label.set_visible(False)
        threading.Thread(target=self._run_test, daemon=True).start()

    def _run_test(self) -> None:
        api_key = self._key_row.get_text().strip()
        whisper = _WHISPER_MODELS[self._whisper_combo.get_selected()]
        llm = _LLM_MODELS[self._llm_combo.get_selected()]

        try:
            from groq import Groq

            client = Groq(api_key=api_key)
            available = {m.id for m in client.models.list().data}

            whisper_ok = whisper in available
            llm_ok = llm in available

            w = "✓" if whisper_ok else "✗"
            l = "✓" if llm_ok else "✗"
            msg = f"Key OK   Whisper {w}   LLM {l}"
            ok = whisper_ok and llm_ok
        except Exception as e:
            err = str(e)
            # Trim verbose Groq error messages to the key part
            if "invalid_api_key" in err.lower() or "401" in err:
                err = "Invalid API key"
            elif "connection" in err.lower():
                err = "No connection"
            msg = f"✗  {err}"
            ok = False

        GLib.idle_add(self._show_result, msg, ok)

    def _show_result(self, msg: str, ok: bool) -> None:
        self._result_label.set_text(msg)
        self._result_label.remove_css_class("success")
        self._result_label.remove_css_class("error")
        self._result_label.add_css_class("success" if ok else "error")
        self._result_label.set_visible(True)
        self._test_btn.set_label("Test")
        self._test_btn.set_sensitive(True)
        GLib.timeout_add_seconds(3, self._reset_result)

    def _reset_result(self) -> bool:
        self._result_label.set_visible(False)
        return False  # don't repeat

    def _on_whisper_changed(self, combo, _) -> None:
        model = _WHISPER_MODELS[combo.get_selected()]
        config.set_value("groq", "whisper_model", model)
        self._engine.reload()

    def _on_llm_changed(self, combo, _) -> None:
        model = _LLM_MODELS[combo.get_selected()]
        config.set_value("groq", "llm_model", model)
        self._engine.reload()
