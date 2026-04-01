"""Main settings window with sidebar navigation."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from ui.pages.about import AboutPage
from ui.pages.advanced import AdvancedPage
from ui.pages.general import GeneralPage
from ui.pages.history import HistoryPage
from ui.pages.models import ModelsPage

_NAV_ITEMS = [
    ("General", "view-list-symbolic", "general"),
    ("Models", "applications-science-symbolic", "models"),
    ("Advanced", "emblem-system-symbolic", "advanced"),
    ("History", "document-open-recent-symbolic", "history"),
    ("About", "help-about-symbolic", "about"),
]

_CSS = b"""
.sidebar {
    background-color: alpha(@window_bg_color, 0.6);
    border-right: 1px solid @borders;
    min-width: 180px;
}
.sidebar row {
    border-radius: 8px;
    margin: 2px 8px;
    padding: 2px 0;
}
.nav-label {
    font-size: 0.95em;
}
"""


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, engine):
        super().__init__(application=app)
        self._engine = engine
        self.set_title("Linux Flow")
        self.set_default_size(820, 580)
        self.set_resizable(True)
        # Dock/taskbar icon — "linux-flow" is installed by install.sh;
        # falls back gracefully to the theme default if not found.
        self.set_icon_name("linux-flow")

        # Apply CSS
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Close hides window instead of quitting app
        self.connect("close-request", self._on_close_request)

        # Root layout
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        # Header bar
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title="Linux Flow", subtitle="Voice Dictation")
        )
        root.append(header)

        # Main content: sidebar + stack
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        content.set_vexpand(True)
        root.append(content)

        # Sidebar
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.add_css_class("sidebar")
        sidebar.set_vexpand(True)
        content.append(sidebar)

        self._nav_list = Gtk.ListBox()
        self._nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._nav_list.set_vexpand(True)
        self._nav_list.set_margin_top(8)
        self._nav_list.add_css_class("navigation-sidebar")
        self._nav_list.connect("row-selected", self._on_nav_selected)
        sidebar.append(self._nav_list)

        for label, icon, page_id in _NAV_ITEMS:
            row = self._make_nav_row(label, icon, page_id)
            self._nav_list.append(row)

        # Page stack
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_UP_DOWN)
        self._stack.set_transition_duration(150)
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)
        content.append(self._stack)

        self._pages = {
            "general": GeneralPage(engine),
            "models": ModelsPage(engine),
            "advanced": AdvancedPage(engine),
            "history": HistoryPage(engine),
            "about": AboutPage(engine),
        }
        for page_id, widget in self._pages.items():
            self._stack.add_named(widget, page_id)

        # Select General by default
        self._nav_list.select_row(self._nav_list.get_row_at_index(0))

        # Refresh history page when a result comes in
        engine.on_result = self._on_result

    def show_page(self, page_id: str) -> None:
        self._stack.set_visible_child_name(page_id)
        for i, (_, _, pid) in enumerate(_NAV_ITEMS):
            if pid == page_id:
                self._nav_list.select_row(self._nav_list.get_row_at_index(i))
                break

    def _make_nav_row(self, label: str, icon: str, page_id: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row._page_id = page_id
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)

        img = Gtk.Image.new_from_icon_name(icon)
        img.set_pixel_size(16)
        box.append(img)

        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0)
        lbl.add_css_class("nav-label")
        box.append(lbl)

        row.set_child(box)
        return row

    def _on_nav_selected(self, listbox, row) -> None:
        if row and hasattr(row, "_page_id"):
            self._stack.set_visible_child_name(row._page_id)
            if row._page_id == "history":
                self._pages["history"].refresh()

    def _on_close_request(self, _) -> bool:
        self.set_visible(False)
        return True  # prevent destroy

    def _on_result(self, raw: str, final: str, injected: bool) -> None:
        GLib.idle_add(self._pages["history"].refresh)
