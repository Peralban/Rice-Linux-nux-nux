"""Widget notifications, adossé à swaync.

swaync ne publie pas la liste des notifications : son client n'expose que
le compteur, l'état « ne pas déranger » et l'ouverture du centre. On montre
donc ce qui existe vraiment, et on délègue le reste au centre de contrôle
plutôt que d'inventer une liste qu'on ne peut pas lire.

Le compteur arrive par `swaync-client --subscribe`, un flux d'événements :
aucun sondage.
"""

import json
import shutil
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

CLIENT = shutil.which("swaync-client")

STRINGS = {
    "fr": {"title": "NOTIFICATIONS", "none": "Rien en attente",
           "one": "1 notification", "many": "{n} notifications",
           "open": "Ouvrir le centre", "dnd_on": "Ne pas déranger : actif",
           "dnd_off": "Ne pas déranger", "clear": "Tout effacer",
           "absent": "swaync n'est pas installé"},
    "en": {"title": "NOTIFICATIONS", "none": "Nothing waiting",
           "one": "1 notification", "many": "{n} notifications",
           "open": "Open the center", "dnd_on": "Do not disturb: on",
           "dnd_off": "Do not disturb", "clear": "Clear all",
           "absent": "swaync is not installed"},
}


class NotificationsWidget(Gtk.Box):
    def __init__(self, lang="fr"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.s = STRINGS.get(lang, STRINGS["fr"])
        self.count = 0
        self.dnd = False
        self.process = None
        self.watch = None

        heading = Gtk.Label(label=self.s["title"], xalign=0)
        heading.add_css_class("nk-sec")
        self.append(heading)

        row = Gtk.Box(spacing=8)
        self.icon = Gtk.Image.new_from_icon_name("preferences-system-notifications-symbolic")
        self.icon.set_pixel_size(20)
        self.summary = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.summary.add_css_class("nk-event-name")
        row.append(self.icon)
        row.append(self.summary)
        self.append(row)

        actions = Gtk.Box(spacing=6)
        actions.set_margin_top(2)
        self.b_open = self._button("view-list-symbolic", self.s["open"],
                                   lambda: self._run("-t"))
        self.b_dnd = self._button("notifications-disabled-symbolic", self.s["dnd_off"],
                                  lambda: self._run("-d"))
        self.b_clear = self._button("edit-clear-all-symbolic", self.s["clear"],
                                    lambda: self._run("-C"))
        for widget in (self.b_open, self.b_dnd, self.b_clear):
            actions.append(widget)
        self.append(actions)

        if CLIENT:
            self._subscribe()
        else:
            self.summary.set_text(self.s["absent"])
            for widget in (self.b_open, self.b_dnd, self.b_clear):
                widget.set_sensitive(False)

    def _button(self, icon, tooltip, action):
        button = Gtk.Button(tooltip_text=tooltip)
        button.set_child(Gtk.Image.new_from_icon_name(icon))
        button.add_css_class("nk-tab")
        button.connect("clicked", lambda *_: action())
        return button

    @staticmethod
    def _run(*args):
        if not CLIENT:
            return
        try:
            subprocess.Popen([CLIENT, *args], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    # --- flux d'événements ----------------------------------------------
    def _subscribe(self):
        try:
            self.process = subprocess.Popen(
                [CLIENT, "-s"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            self.summary.set_text(self.s["absent"])
            return
        channel = GLib.IOChannel.unix_new(self.process.stdout.fileno())
        channel.set_flags(GLib.IOFlags.NONBLOCK)
        self.watch = GLib.io_add_watch(channel, GLib.PRIORITY_DEFAULT,
                                       GLib.IOCondition.IN | GLib.IOCondition.HUP,
                                       self._on_line)
        self.refresh()

    def _on_line(self, channel, condition):
        if condition & GLib.IOCondition.HUP:
            return False
        try:
            line, _length, _term = channel.read_line()
        except (GLib.Error, ValueError):
            return True
        if line:
            try:
                data = json.loads(line)
                self.count = int(data.get("count", 0))
                self.dnd = bool(data.get("dnd", False))
                self._render()
            except (ValueError, TypeError):
                pass
        return True

    def refresh(self):
        if not CLIENT:
            return
        try:
            out = subprocess.run([CLIENT, "-c"], capture_output=True, text=True, timeout=2)
            self.count = int(out.stdout.strip() or 0)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        self._render()

    def _render(self):
        if self.count == 0:
            self.summary.set_text(self.s["none"])
            self.summary.add_css_class("nk-empty")
        else:
            self.summary.remove_css_class("nk-empty")
            self.summary.set_text(self.s["one"] if self.count == 1
                                  else self.s["many"].format(n=self.count))
        self.b_dnd.set_tooltip_text(self.s["dnd_on"] if self.dnd else self.s["dnd_off"])
        if self.dnd:
            self.b_dnd.add_css_class("nk-on")
        else:
            self.b_dnd.remove_css_class("nk-on")

    def shutdown(self):
        if self.watch:
            GLib.source_remove(self.watch)
            self.watch = None
        if self.process:
            self.process.terminate()
            self.process = None
