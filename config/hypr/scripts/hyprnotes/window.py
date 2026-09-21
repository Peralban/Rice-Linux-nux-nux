"""HyprNotes' window: one sidebar, one note.

The sidebar floats over the text rather than pushing it
(`Adw.OverlaySplitView` collapsed). It opens three ways -- the mouse at the
left edge, Ctrl+B, the header button -- and tells two of them apart: on hover
it is transient and closes when the mouse leaves, from the keyboard it stays
until closed. The same logic as the notch, which already separates `open`
from `pinned`.
"""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import markup
from .store import Store, clean

LANG_FILE = os.path.expanduser("~/.config/hypr/scripts/.hyprsettings-lang")

# Delay before writing to disk, measured from the last keystroke.
SAVE_MS = 500
# Width of the sensitive strip at the left edge, and anti-flicker.
EDGE_PX = 6
OPEN_MS = 120
CLOSE_MS = 220
SIDEBAR_PX = 280

T = {
    "fr": {
        "window": "Notes",
        "search": "Rechercher…",
        "new": "Nouvelle note",
        "delete": "Supprimer",
        "delete_q": "Supprimer cette note ?",
        "delete_body": "Le fichier sera effacé. C'est sans retour.",
        "cancel": "Annuler",
        "sidebar": "Afficher les notes",
        "pin": "Garder en haut de la liste",
        "unpin": "Ne plus garder en haut",
        "notch": "Afficher dans le notch",
        "unnotch": "Retirer du notch",
        "empty": "Aucune note",
        "empty_sub": "Crée la première, elle apparaîtra ici",
        "none": "Aucune note ne correspond",
        "placeholder": "Écris…",
        "deleted": "Note supprimée",
        "untitled": "Sans titre",
        "today": "Aujourd'hui",
    },
    "en": {
        "window": "Notes",
        "search": "Search…",
        "new": "New note",
        "delete": "Delete",
        "delete_q": "Delete this note?",
        "delete_body": "The file will be erased. There is no undo.",
        "cancel": "Cancel",
        "sidebar": "Show notes",
        "pin": "Keep at the top",
        "unpin": "Stop keeping at the top",
        "notch": "Show in the notch",
        "unnotch": "Remove from the notch",
        "empty": "No notes",
        "empty_sub": "Create the first one, it shows up here",
        "none": "No note matches",
        "placeholder": "Write…",
        "deleted": "Note deleted",
        "untitled": "Untitled",
        "today": "Today",
    },
}

CSS = """
.hn-note { font-family: "JetBrainsMono Nerd Font Propo", "JetBrains Mono", monospace; }
.hn-note text { background: transparent; }
.hn-row-title { font-weight: 700; }
.hn-row-preview { font-size: 0.85em; opacity: 0.6; }
.hn-row-date { font-size: 0.78em; opacity: 0.45; }
.hn-sidebar { background: @sidebar_bg_color; }
.hn-flag { min-width: 24px; min-height: 24px; padding: 0; }
"""


def lang():
    try:
        with open(LANG_FILE, encoding="utf-8") as fh:
            value = fh.read().strip()
            if value in ("fr", "en"):
                return value
    except OSError:
        pass
    return "fr"


def stamp(mtime):
    """A short date: the time today, the day this year, otherwise the full
    date. Reading "14:32" beats "15/09/2026 14:32" when the note is ten
    minutes old."""
    when = GLib.DateTime.new_from_unix_local(int(mtime))
    now = GLib.DateTime.new_now_local()
    if when.get_ymd() == now.get_ymd():
        return when.format("%H:%M")
    if when.get_year() == now.get_year():
        return when.format("%d %b")
    return when.format("%d/%m/%y")


class NoteRow(Gtk.ListBoxRow):
    """One row of the list: title, preview, date, and the two pins."""

    def __init__(self, note, strings, pinned, in_notch, on_pin, on_notch):
        super().__init__()
        self.note_id = note.id

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(10)
        box.set_margin_end(6)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        title = Gtk.Label(label=note.title(strings["untitled"]), xalign=0, ellipsize=3)
        title.add_css_class("hn-row-title")
        column.append(title)

        preview = note.preview()
        if preview:
            label = Gtk.Label(label=preview, xalign=0, ellipsize=3)
            label.add_css_class("hn-row-preview")
            column.append(label)

        date = Gtk.Label(label=stamp(note.mtime), xalign=0)
        date.add_css_class("hn-row-date")
        column.append(date)
        box.append(column)

        flags = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                        valign=Gtk.Align.CENTER)
        flags.append(self._flag("view-pin-symbolic", pinned,
                                strings["unpin"] if pinned else strings["pin"],
                                lambda: on_pin(note.id)))
        flags.append(self._flag("video-display-symbolic", in_notch,
                                strings["unnotch"] if in_notch else strings["notch"],
                                lambda: on_notch(note.id)))
        box.append(flags)
        self.set_child(box)

    @staticmethod
    def _flag(icon, active, tooltip, action):
        button = Gtk.Button(tooltip_text=tooltip, valign=Gtk.Align.CENTER)
        button.set_child(Gtk.Image.new_from_icon_name(icon))
        button.add_css_class("flat")
        button.add_css_class("hn-flag")
        if active:
            button.add_css_class("accent")
        else:
            button.set_opacity(0.35)
        button.connect("clicked", lambda *_: action())
        return button


class NotesWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=T[lang()]["window"])
        self.s = T[lang()]
        self.store = Store()
        self.current = None
        self.dirty = False
        self.save_timer = None
        self.edge_timer = None
        self.sidebar_pinned = False
        self.set_default_size(880, 620)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.split = Adw.OverlaySplitView(
            collapsed=True, show_sidebar=False,
            sidebar_width_fraction=0.32, max_sidebar_width=SIDEBAR_PX)
        self.split.set_sidebar(self._sidebar())
        self.split.set_content(self._content())

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        self._bind_keys()
        self._bind_edge()
        # GTK4 destroys the window by default on `close-request`: after a
        # click on the cross the process stayed alive but the shortcut had
        # nothing left to bring back. We hide, we never destroy.
        self.connect("close-request", self._on_close_request)

        self.store.watch(self._on_disk_change)
        self.reload_list()
        notes = self.store.list()
        self.open_note(notes[0].id if notes else self.store.create())

    # --- construction ---------------------------------------------------
    def _sidebar(self):
        view = Adw.ToolbarView()
        view.add_css_class("hn-sidebar")

        header = Adw.HeaderBar(show_title=False)
        add = Gtk.Button(icon_name="document-new-symbolic", tooltip_text=self.s["new"])
        add.connect("clicked", lambda *_: self.new_note())
        header.pack_end(add)
        view.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.search = Gtk.SearchEntry(placeholder_text=self.s["search"])
        self.search.set_margin_start(8)
        self.search.set_margin_end(8)
        self.search.connect("search-changed", lambda *_: self.reload_list())
        box.append(self.search)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("navigation-sidebar")
        self.list.connect("row-activated", self._on_row)

        self.empty = Adw.StatusPage(icon_name="document-new-symbolic",
                                    title=self.s["empty"],
                                    description=self.s["empty_sub"])
        self.list_stack = Gtk.Stack()
        self.list_stack.add_named(self.list, "list")
        self.list_stack.add_named(self.empty, "empty")

        scroll = Gtk.ScrolledWindow(vexpand=True,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.list_stack)
        box.append(scroll)
        view.set_content(box)
        return view

    def _content(self):
        view = Adw.ToolbarView()

        self.header = Adw.HeaderBar()
        toggle = Gtk.Button(icon_name="sidebar-show-symbolic",
                            tooltip_text=self.s["sidebar"])
        toggle.connect("clicked", lambda *_: self.toggle_sidebar())
        self.header.pack_start(toggle)

        self.heading = Adw.WindowTitle(title=self.s["window"])
        self.header.set_title_widget(self.heading)

        trash = Gtk.Button(icon_name="user-trash-symbolic",
                           tooltip_text=self.s["delete"])
        trash.add_css_class("flat")
        trash.connect("clicked", lambda *_: self.ask_delete())
        self.header.pack_end(trash)
        view.add_top_bar(self.header)

        self.text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 left_margin=18, right_margin=18,
                                 top_margin=14, bottom_margin=14)
        self.text.add_css_class("hn-note")
        self.text.get_buffer().set_enable_undo(True)
        self.markup = markup.attach(self.text)
        self.text.get_buffer().connect("changed", self._on_typed)

        scroll = Gtk.ScrolledWindow(vexpand=True,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.text)
        view.set_content(scroll)
        return view

    def _bind_keys(self):
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

    def _bind_edge(self):
        """The mouse at the left edge opens the sidebar. The controller sits on
        the window in the capture phase: otherwise the text view swallows the
        motion before we see it."""
        motion = Gtk.EventControllerMotion()
        motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        motion.connect("motion", self._on_motion)
        self.add_controller(motion)

    # --- sidebar --------------------------------------------------------
    def toggle_sidebar(self):
        if self.split.get_show_sidebar():
            self.close_sidebar()
        else:
            self.sidebar_pinned = True
            self.split.set_show_sidebar(True)

    def close_sidebar(self):
        self.sidebar_pinned = False
        self._cancel_edge()
        self.split.set_show_sidebar(False)

    def _cancel_edge(self):
        if self.edge_timer is not None:
            GLib.source_remove(self.edge_timer)
            self.edge_timer = None

    def _on_motion(self, _controller, x, _y):
        shown = self.split.get_show_sidebar()
        if not shown and x <= EDGE_PX:
            self._arm_edge(OPEN_MS, True)
        elif shown and not self.sidebar_pinned and x > SIDEBAR_PX + 24:
            self._arm_edge(CLOSE_MS, False)
        else:
            self._cancel_edge()

    def _arm_edge(self, delay, show):
        if self.edge_timer is not None:
            return

        def fire():
            self.edge_timer = None
            self.split.set_show_sidebar(show)
            if not show:
                self.sidebar_pinned = False
            return False

        self.edge_timer = GLib.timeout_add(delay, fire)

    # --- liste ----------------------------------------------------------
    def reload_list(self):
        needle = self.search.get_text().strip().lower() if hasattr(self, "search") else ""
        notes = self.store.list()
        if needle:
            notes = [n for n in notes if needle in n.text.lower()
                     or needle in n.title(self.s["untitled"]).lower()]

        while True:
            row = self.list.get_row_at_index(0)
            if row is None:
                break
            self.list.remove(row)

        pinned = set(self.store.pinned())
        in_notch = self.store.notch_note()
        for note in notes:
            self.list.append(NoteRow(note, self.s, note.id in pinned,
                                     note.id == in_notch,
                                     self._on_pin, self._on_notch))

        if not notes:
            self.empty.set_title(self.s["none"] if needle else self.s["empty"])
            self.empty.set_description("" if needle else self.s["empty_sub"])
        self.list_stack.set_visible_child_name("list" if notes else "empty")
        self._mark_selected()

    def _mark_selected(self):
        index = 0
        while True:
            row = self.list.get_row_at_index(index)
            if row is None:
                return
            if row.note_id == self.current:
                self.list.select_row(row)
                return
            index += 1

    def _on_row(self, _list, row):
        if row is not None and row.note_id != self.current:
            self.open_note(row.note_id)
        if not self.sidebar_pinned:
            self.close_sidebar()

    def _on_pin(self, note_id):
        self.store.toggle_pin(note_id)
        self.reload_list()

    def _on_notch(self, note_id):
        self.store.set_notch_note(note_id)
        self.reload_list()

    # --- note courante --------------------------------------------------
    def open_note(self, note_id):
        self.flush()
        note = self.store.read(note_id)
        if note is None:
            return
        self.current = note_id
        buffer = self.text.get_buffer()
        buffer.set_enable_undo(False)
        buffer.set_text(note.text)
        buffer.set_enable_undo(True)
        self.dirty = False
        self.markup.follow(self.text)
        self.markup.apply()
        self.heading.set_title(note.title(self.s["untitled"]))
        self._mark_selected()

    def new_note(self):
        self.flush()
        note_id = self.store.create()
        self.reload_list()
        self.open_note(note_id)
        self.text.grab_focus()
        if not self.sidebar_pinned:
            self.close_sidebar()

    def _on_typed(self, buffer):
        self.dirty = True
        self.heading.set_title(
            self._first_line(buffer) or self.s["untitled"])
        if self.save_timer is not None:
            GLib.source_remove(self.save_timer)
        self.save_timer = GLib.timeout_add(SAVE_MS, self._save)

    @staticmethod
    def _first_line(buffer):
        start, end = buffer.get_bounds()
        for line in buffer.get_text(start, end, False).splitlines():
            cleaned = clean(line)
            if cleaned:
                return cleaned
        return ""

    def _save(self):
        self.save_timer = None
        self.flush()
        self.reload_list()
        return False

    def flush(self):
        """Writes the current note if it changed. Called before anything that
        could lose it: switching notes, closing, deleting."""
        if not self.dirty or self.current is None:
            return
        self.store.write(self.current, self.markup.serialize())
        self.dirty = False

    # --- suppression ----------------------------------------------------
    def ask_delete(self):
        if self.current is None:
            return
        dialog = Adw.AlertDialog(heading=self.s["delete_q"],
                                 body=self.s["delete_body"])
        dialog.add_response("cancel", self.s["cancel"])
        dialog.add_response("delete", self.s["delete"])
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_delete)
        dialog.present(self)

    def _on_delete(self, _dialog, response):
        if response != "delete" or self.current is None:
            return
        self.dirty = False
        self.store.delete(self.current)
        self.current = None
        self.reload_list()
        notes = self.store.list()
        self.open_note(notes[0].id if notes else self.store.create())
        self.toasts.add_toast(Adw.Toast(title=self.s["deleted"], timeout=2))

    # --- outside events -------------------------------------------------
    def _on_disk_change(self):
        """The notch wrote, or nvim, or a sync. The list always follows; the
        open note only if it is not being typed into -- we are not going to
        overwrite a keystroke in progress."""
        self.reload_list()
        if self.dirty or self.current is None:
            return
        note = self.store.read(self.current)
        if note is None:
            return
        buffer = self.text.get_buffer()
        if self.markup.serialize() == note.text:
            return
        # Keep the caret where it was: the note moved, not the intent.
        offset = buffer.get_property("cursor-position")
        buffer.set_enable_undo(False)
        buffer.set_text(note.text)
        buffer.set_enable_undo(True)
        self.dirty = False
        self.markup.apply()
        buffer.place_cursor(buffer.get_iter_at_offset(
            min(offset, buffer.get_char_count())))

    def _on_key(self, _controller, keyval, _code, state):
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if keyval == Gdk.KEY_Escape:
            if self.split.get_show_sidebar():
                self.close_sidebar()
            else:
                self.close_window()
            return True
        if ctrl and keyval in (Gdk.KEY_b, Gdk.KEY_B):
            self.toggle_sidebar()
            return True
        if ctrl and keyval in (Gdk.KEY_n, Gdk.KEY_N):
            self.new_note()
            return True
        if ctrl and keyval in (Gdk.KEY_f, Gdk.KEY_F):
            self.sidebar_pinned = True
            self.split.set_show_sidebar(True)
            self.search.grab_focus()
            return True
        if ctrl and keyval in (Gdk.KEY_w, Gdk.KEY_W):
            self.close_window()
            return True
        return False

    def _on_close_request(self, *_):
        self.close_window()
        return True

    def close_window(self):
        self.flush()
        self.set_visible(False)

    def reload_theme(self):
        """Called on SIGUSR1, once matugen has regenerated the palette."""
        Gtk.Settings.get_default().reset_property("gtk-theme-name")
        self.markup.follow(self.text)
        self.markup.apply()

    def toggle_window(self):
        """SIGUSR2: the shortcut opens, then hides."""
        if self.get_visible():
            self.close_window()
        else:
            self.set_visible(True)
            self.present()
