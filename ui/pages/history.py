"""History page — browse and copy past transcriptions."""

from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from db import history as db


def _fmt_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%B %d, %Y  %I:%M %p")
    except Exception:
        return iso


def _fmt_duration(secs: float | None) -> str:
    if secs is None:
        return ""
    return f"{secs:.1f}s"


class HistoryRow(Gtk.ListBoxRow):
    def __init__(self, entry: dict):
        super().__init__()
        self._entry = entry
        self.set_activatable(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Top row: timestamp + mode badge + duration
        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        meta_box.set_halign(Gtk.Align.START)

        date_label = Gtk.Label(label=_fmt_date(entry["created_at"]))
        date_label.add_css_class("caption")
        date_label.add_css_class("dim-label")
        meta_box.append(date_label)

        mode_badge = Gtk.Label(label=entry.get("mode", "raw"))
        mode_badge.add_css_class("caption")
        mode_badge.add_css_class("accent")
        meta_box.append(mode_badge)

        dur = _fmt_duration(entry.get("duration_s"))
        if dur:
            dur_label = Gtk.Label(label=dur)
            dur_label.add_css_class("caption")
            dur_label.add_css_class("dim-label")
            meta_box.append(dur_label)

        box.append(meta_box)

        # Final text
        text_label = Gtk.Label(label=entry["final_text"])
        text_label.set_wrap(True)
        text_label.set_xalign(0)
        text_label.set_max_width_chars(80)
        box.append(text_label)

        # If enhanced, show raw in muted text
        if entry.get("raw_text") and entry["raw_text"] != entry["final_text"]:
            raw_label = Gtk.Label(label=f"Raw: {entry['raw_text']}")
            raw_label.set_wrap(True)
            raw_label.set_xalign(0)
            raw_label.add_css_class("caption")
            raw_label.add_css_class("dim-label")
            box.append(raw_label)

        self.set_child(box)

    @property
    def final_text(self) -> str:
        return self._entry["final_text"]

    @property
    def entry_id(self) -> int:
        return self._entry["id"]


class HistoryPage(Gtk.Box):
    def __init__(self, engine):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._engine = engine
        engine.on_result = self._on_new_result

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_top(12)
        toolbar.set_margin_bottom(8)
        toolbar.set_margin_start(16)
        toolbar.set_margin_end(16)

        title = Gtk.Label(label="Transcription History")
        title.add_css_class("title-4")
        title.set_hexpand(True)
        title.set_xalign(0)
        toolbar.append(title)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.add_css_class("flat")
        refresh_btn.set_tooltip_text("Refresh")
        refresh_btn.connect("clicked", lambda _: self.refresh())
        toolbar.append(refresh_btn)

        clear_btn = Gtk.Button(icon_name="edit-delete-symbolic")
        clear_btn.add_css_class("flat")
        clear_btn.add_css_class("destructive-action")
        clear_btn.set_tooltip_text("Clear all history")
        clear_btn.connect("clicked", self._on_clear)
        toolbar.append(clear_btn)

        self.append(toolbar)

        sep = Gtk.Separator()
        self.append(sep)

        # Copy hint
        hint = Gtk.Label(label="Click any entry to copy it to the clipboard")
        hint.add_css_class("caption")
        hint.add_css_class("dim-label")
        hint.set_margin_top(4)
        hint.set_margin_bottom(4)
        self.append(hint)

        # Scrollable list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_margin_top(8)
        self._list_box.set_margin_bottom(8)
        self._list_box.set_margin_start(16)
        self._list_box.set_margin_end(16)
        self._list_box.connect("row-activated", self._on_row_activated)
        scroll.set_child(self._list_box)

        self._toast_overlay = None  # set by window
        self.refresh()

    def refresh(self) -> None:
        # Clear existing rows
        while row := self._list_box.get_row_at_index(0):
            self._list_box.remove(row)

        entries = db.get_recent(100)
        if not entries:
            placeholder = Gtk.Label(
                label="No transcriptions yet.\nStart recording with Ctrl+Space."
            )
            placeholder.add_css_class("dim-label")
            placeholder.set_justify(Gtk.Justification.CENTER)
            placeholder.set_margin_top(40)
            self._list_box.append(placeholder)
            return

        for entry in entries:
            self._list_box.append(HistoryRow(entry))

    def _on_row_activated(self, listbox, row) -> None:
        if isinstance(row, HistoryRow):
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(row.final_text)
            print(f"Copied: {row.final_text[:60]}...")

    def _on_clear(self, _) -> None:
        dialog = Adw.AlertDialog(
            heading="Clear History?",
            body="This will permanently delete all transcription history.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete All")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_clear_response)
        dialog.present(self)

    def _on_clear_response(self, dialog, response) -> None:
        if response == "delete":
            db.clear_all()
            self.refresh()

    def _on_new_result(self, raw: str, final: str, injected: bool) -> None:
        GLib.idle_add(self.refresh)
