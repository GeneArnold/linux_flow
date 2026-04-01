"""Models settings page — Groq API key and model selection."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

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
        key_row.connect("changed", self._on_key_changed)
        self._key_row = key_row
        api_group.add(key_row)

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

    def _on_key_changed(self, row) -> None:
        pass  # saved on apply (Enter) or focus-out

    def _on_key_apply(self, row) -> None:
        config.set_value("groq", "api_key", row.get_text())
        self._engine.reload()

    def _on_whisper_changed(self, combo, _) -> None:
        model = _WHISPER_MODELS[combo.get_selected()]
        config.set_value("groq", "whisper_model", model)
        self._engine.reload()

    def _on_llm_changed(self, combo, _) -> None:
        model = _LLM_MODELS[combo.get_selected()]
        config.set_value("groq", "llm_model", model)
        self._engine.reload()
