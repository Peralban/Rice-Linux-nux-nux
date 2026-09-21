"""Assembly: theme, media service, window.

Signals, as elsewhere in this repository:
  SIGUSR1  reload the palette (matugen)
  SIGUSR2  open / close the notch (keyboard shortcut)
"""

import os
import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from .core.config import LANG_FILE, Config, lang
from .integrations.mpris import Media
from .theme.matugen import Theme
from .ui.notch import Notch

APP_ID = "dev.local.HyprNotch"


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.config = Config()
        self.config.write_default()
        self.notch = None
        self.theme = None
        self.media = None
        self.lang = lang()
        self.lang_monitor = None

    def do_activate(self):
        if self.notch is not None:
            self.notch.present()
            return

        self.theme = Theme(self.config, on_change=self._on_theme)
        self.media = Media(on_update=self._on_media)
        self.notch = Notch(self, self.config, self.media, self.lang)
        self._watch_language()
        self.notch.present()
        self.notch.refresh()
        self.hold()

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self._on_sigusr1)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, self._on_sigusr2)

    def _watch_language(self):
        """Follow the language file the way the theme follows the palette.

        Every string is chosen when the widgets are built, so the language was
        read once and never again: the notch only ever changed language
        because HyprSettings restarts it after writing the file. Anything else
        that wrote it -- a script, an editor, a second settings window -- left
        the two disagreeing with no way to tell.

        Watching the file makes the notch answer to the setting rather than to
        whoever happens to restart it.
        """
        try:
            gfile = Gio.File.new_for_path(LANG_FILE)
            self.lang_monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self.lang_monitor.connect("changed", self._on_lang_event)
        except GLib.Error:
            pass

    def _on_lang_event(self, _monitor, _file, _other, event):
        if event not in (Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                         Gio.FileMonitorEvent.CREATED,
                         Gio.FileMonitorEvent.RENAMED):
            return
        if lang() == self.lang:
            return
        # Rebuilding every string in place would mean re-creating the whole
        # widget tree; re-executing is the same thing, honestly, and is what
        # HyprSettings already does from outside.
        GLib.timeout_add(150, self._relaunch)

    @staticmethod
    def _relaunch():
        os.execv(sys.executable, [sys.executable, *sys.argv])
        return False

    def _on_media(self):
        if self.notch:
            self.notch.refresh()
        return False

    def _on_theme(self):
        if self.notch:
            self.notch.reload_theme()

    def _on_sigusr1(self):
        if self.theme:
            self.theme.reload()
        return True

    def _on_sigusr2(self):
        if self.notch:
            self.notch.toggle()
        return True


def main():
    App().run(None)
