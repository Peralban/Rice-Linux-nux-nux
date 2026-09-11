"""Étagère à fichiers : on dépose, on récupère ailleurs.

Rien n'est copié ni déplacé. L'étagère ne retient que des chemins, et
chaque ligne est elle-même une source de glisser-déposer : on ressort le
fichier vers un gestionnaire, un terminal, un champ d'upload.
"""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

MAX_ITEMS = 12

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

        # état vide : la zone pointillée, comme une vraie cible de dépôt
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

    # --- contenu --------------------------------------------------------
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
        icon = Gtk.Image(pixel_size=16)
        icon.set_from_gicon(self._icon_for(gfile))
        row.append(icon)

        name = Gtk.Label(label=os.path.basename(path), xalign=0, ellipsize=3, hexpand=True)
        name.add_css_class("nk-file-name")
        name.set_tooltip_text(path)
        row.append(name)

        # ressortir le fichier
        source = Gtk.DragSource(actions=Gdk.DragAction.COPY)
        source.connect("prepare", lambda *_: Gdk.ContentProvider.new_typed(Gio.File, gfile))
        row.add_controller(source)

        # ouvrir
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self._open(gfile))
        row.add_controller(click)
        return row

    @staticmethod
    def _icon_for(gfile):
        try:
            info = gfile.query_info("standard::icon", Gio.FileQueryInfoFlags.NONE, None)
            return info.get_icon()
        except GLib.Error:
            return Gio.ThemedIcon.new("text-x-generic-symbolic")

    @staticmethod
    def _open(gfile):
        launcher = Gtk.FileLauncher.new(gfile)
        launcher.launch(None, None, None, None)
