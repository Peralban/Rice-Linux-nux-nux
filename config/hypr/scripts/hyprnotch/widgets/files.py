"""File shelf: drop here, pick up elsewhere.

Nothing is copied or moved. The shelf holds only paths, and each row is itself
a drag source: the file goes back out to a file manager, a terminal, an upload
field.
"""

import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk  # noqa: E402

MAX_ITEMS = 12

# Thumbnail side. Large enough to recognise an image at a glance, small enough
# that twelve rows fit in the panel.
THUMB = 24

# Thumbnails already decoded, keyed by path and file fingerprint. The shelf is
# redrawn in full on every drop: without this we re-ran one decode per row per
# addition.
PREVIEWS = {}

STRINGS = {
    "fr": {"title": "FICHIERS", "drop": "Déposer des fichiers ici",
           "hint": "glisse-les dehors pour les récupérer",
           "clear": "Vider l'étagère", "open": "Ouvrir",
           "count": "{n} en attente"},
    "en": {"title": "FILES", "drop": "Drop files here",
           "hint": "drag them out to pick them up",
           "clear": "Clear the shelf", "open": "Open",
           "count": "{n} waiting"},
}


def content_for(gfile):
    """Offers the file in every shape a target might want.

    `Gdk.ContentProvider.new_typed()` does not exist in the Python bindings:
    calling it raised inside the `prepare` handler, and no drag ever started.
    It has to go through GValues.
    """
    parts = []

    files = GObject.Value(Gdk.FileList)
    files.set_boxed(Gdk.FileList.new_from_list([gfile]))
    parts.append(Gdk.ContentProvider.new_for_value(files))

    single = GObject.Value(Gio.File)
    single.set_object(gfile)
    parts.append(Gdk.ContentProvider.new_for_value(single))

    parts.append(Gdk.ContentProvider.new_for_bytes(
        "text/uri-list", GLib.Bytes.new((gfile.get_uri() + "\r\n").encode())))

    return Gdk.ContentProvider.new_union(parts)


def stamp_of(path):
    """Identifies a version of the file, not merely its name."""
    try:
        info = os.stat(path)
        return (path, info.st_mtime, info.st_size)
    except OSError:
        return (path, 0, 0)


def load_preview(path, size, done):
    """Looks for a thumbnail and calls back `done(texture)` on the GTK loop.
    Calls back nothing if the file has no image to show."""
    try:
        info = Gio.File.new_for_path(path).query_info(
            "standard::content-type,thumbnail::path,thumbnail::is-valid",
            Gio.FileQueryInfoFlags.NONE, None)
    except GLib.Error:
        return

    # The desktop thumbnail first: free, already the right size, and it covers
    # the videos and PDFs we could not render ourselves. The flag matters as
    # much as the path -- the cached file often exists when it no longer matches
    # what we are looking at.
    if info.get_attribute_boolean("thumbnail::is-valid"):
        cached = info.get_attribute_byte_string("thumbnail::path")
        if cached and os.path.exists(cached):
            decode(cached, size, done)
            return

    if (info.get_content_type() or "").startswith("image/"):
        decode(path, size, done)


def decode(source, size, done):
    """Decoding goes to a thread: measured at 85 ms for a 1.6 MB PNG, enough
    to make the notch stutter on every drop."""
    def work():
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                source, size, size, True)
        except GLib.Error:
            return
        # The texture is built on the main loop: it touches rendering, and the
        # worker thread has no business there.
        GLib.idle_add(lambda: done(Gdk.Texture.new_for_pixbuf(pixbuf)))

    threading.Thread(target=work, daemon=True).start()


class FilesWidget(Gtk.Box):
    def __init__(self, lang="fr"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.s = STRINGS.get(lang, STRINGS["fr"])
        self.paths = []

        header = Gtk.Box(spacing=6)
        self.heading = Gtk.Label(label=self.s["title"], xalign=0, hexpand=True)
        self.heading.add_css_class("nk-sec")
        self.clear = Gtk.Button(tooltip_text=self.s["clear"], valign=Gtk.Align.CENTER)
        self.clear.set_child(Gtk.Image.new_from_icon_name("edit-clear-all-symbolic"))
        self.clear.add_css_class("nk-tab")
        self.clear.connect("clicked", lambda *_: self.reset())
        header.append(self.heading)
        header.append(self.clear)
        self.append(header)

        # empty state: the dashed area, like a real drop target
        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                             valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER,
                             vexpand=True)
        self.empty.add_css_class("nk-drop")
        icon = Gtk.Image.new_from_icon_name("document-save-symbolic")
        icon.set_pixel_size(20)
        icon.add_css_class("nk-meta")
        label = Gtk.Label(label=self.s["drop"])
        label.add_css_class("nk-empty")
        hint = Gtk.Label(label=self.s["hint"])
        hint.add_css_class("nk-meta")
        for widget in (icon, label, hint):
            self.empty.append(widget)
        self.append(self.empty)

        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, vexpand=True)
        self.scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            propagate_natural_height=False, vexpand=True)
        self.scroller.set_child(self.list)
        self.append(self.scroller)

        self._render()

    # --- content --------------------------------------------------------
    def add(self, paths):
        for path in paths:
            if path and path not in self.paths:
                self.paths.append(path)
        self.paths = self.paths[-MAX_ITEMS:]
        self._render()

    def reset(self):
        self.paths = []
        self._render()

    def _render(self):
        child = self.list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.list.remove(child)
            child = nxt

        has = bool(self.paths)
        self.empty.set_visible(not has)
        self.scroller.set_visible(has)
        self.clear.set_visible(has)
        self.heading.set_text(self.s["title"] if not has
                              else self.s["count"].format(n=len(self.paths)))

        for path in self.paths:
            self.list.append(self._row(path))

    def _row(self, path):
        row = Gtk.Box(spacing=7)
        row.add_css_class("nk-file")

        gfile = Gio.File.new_for_path(path)
        icon = Gtk.Image(pixel_size=THUMB)
        icon.set_from_gicon(self._icon_for(gfile))
        row.append(icon)
        # The theme icon serves as both placeholder and fallback: if the file
        # is not an image, or decoding fails, it stays.
        self._attach_preview(path, icon)

        name = Gtk.Label(label=os.path.basename(path), xalign=0, ellipsize=3, hexpand=True)
        name.add_css_class("nk-file-name")
        name.set_tooltip_text(path)
        row.append(name)

        # send the file back out
        source = Gtk.DragSource(actions=Gdk.DragAction.COPY)
        source.connect("prepare", lambda *_: content_for(gfile))
        source.connect("drag-begin", lambda _s, drag: self._set_drag_icon(drag, icon))
        row.add_controller(source)

        # open
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self._open(gfile))
        row.add_controller(click)
        return row

    def _attach_preview(self, path, image):
        stamp = stamp_of(path)
        cached = PREVIEWS.get(stamp)
        if cached is not None:
            self._show_preview(image, cached)
            return

        def done(texture):
            PREVIEWS[stamp] = texture
            self._show_preview(image, texture)
            return False

        # Twice the displayed size: HiDPI screens render the thumbnail at their
        # own scale, and a pixel-exact texture would blur there.
        load_preview(path, THUMB * 2, done)

    @staticmethod
    def _show_preview(image, texture):
        image.set_from_paintable(texture)
        image.add_css_class("nk-thumb")

    @staticmethod
    def _icon_for(gfile):
        try:
            info = gfile.query_info("standard::icon", Gio.FileQueryInfoFlags.NONE, None)
            return info.get_icon()
        except GLib.Error:
            return Gio.ThemedIcon.new("text-x-generic-symbolic")

    @staticmethod
    def _set_drag_icon(drag, icon):
        paintable = icon.get_paintable()
        if paintable is not None:
            Gtk.DragIcon.set_from_paintable(drag, paintable, 8, 8)

    @staticmethod
    def _open(gfile):
        launcher = Gtk.FileLauncher.new(gfile)
        launcher.launch(None, None, None, None)
