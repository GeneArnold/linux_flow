"""About page — app info and credits."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk


class AboutPage(Gtk.Box):
    def __init__(self, engine):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        outer.set_margin_top(48)
        outer.set_margin_bottom(24)
        outer.set_margin_start(40)
        outer.set_margin_end(40)
        outer.set_valign(Gtk.Align.CENTER)
        outer.set_vexpand(True)
        self.append(outer)

        icon = Gtk.Image.new_from_icon_name("audio-input-microphone")
        icon.set_pixel_size(80)
        outer.append(icon)

        name = Gtk.Label(label="Linux Flow")
        name.add_css_class("title-1")
        name.set_margin_top(12)
        outer.append(name)

        tagline = Gtk.Label(label="Voice dictation for Linux")
        tagline.add_css_class("title-4")
        tagline.add_css_class("dim-label")
        outer.append(tagline)

        desc = Gtk.Label(
            label=(
                "Hold a hotkey, speak, release — your words appear instantly wherever\n"
                "your cursor is. Powered by Groq's ultra-fast Whisper API for\n"
                "transcription and Llama for optional AI text enhancement.\n\n"
                "Free and open source. No subscription. No data stored in the cloud."
            )
        )
        desc.set_justify(Gtk.Justification.CENTER)
        desc.add_css_class("body")
        desc.set_margin_top(20)
        outer.append(desc)

        credits = Gtk.Label(label="Designed by Gene Arnold · Built by Claude Code")
        credits.add_css_class("caption")
        credits.add_css_class("dim-label")
        credits.set_margin_top(8)
        outer.append(credits)

        # Tip link placeholder — replace with real URL when available
        # tip_btn = Gtk.LinkButton(uri="https://...", label="Buy me a coffee ☕")
        # outer.append(tip_btn)

        sep = Gtk.Separator()
        sep.set_margin_top(24)
        sep.set_margin_bottom(24)
        outer.append(sep)

        info_group = Adw.PreferencesGroup()
        outer.append(info_group)

        groq_row = Adw.ActionRow(
            title="Transcription",
            subtitle="Groq Whisper large-v3",
        )
        groq_row.add_prefix(Gtk.Image.new_from_icon_name("audio-x-generic-symbolic"))
        info_group.add(groq_row)

        ai_row = Adw.ActionRow(
            title="AI Enhancement",
            subtitle="Groq Llama 3.3 70b",
        )
        ai_row.add_prefix(Gtk.Image.new_from_icon_name("applications-science-symbolic"))
        info_group.add(ai_row)

        ui_row = Adw.ActionRow(
            title="UI Framework",
            subtitle="GTK4 + libadwaita 1.5",
        )
        ui_row.add_prefix(
            Gtk.Image.new_from_icon_name("applications-graphics-symbolic")
        )
        info_group.add(ui_row)

        source_row = Adw.ActionRow(
            title="Source Code",
            subtitle="github.com/GeneArnold/linux_flow",
        )
        source_row.add_prefix(
            Gtk.Image.new_from_icon_name("system-software-install-symbolic")
        )
        info_group.add(source_row)
