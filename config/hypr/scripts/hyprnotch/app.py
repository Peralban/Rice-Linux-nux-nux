"""Assembly: theme, media service, window.

Signals, as elsewhere in this repository:
  SIGUSR1  reload the palette (matugen)
  SIGUSR2  open / close the notch (keyboard shortcut)
"""

import signal

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib  # noqa: E402

from .core.config import Config, lang
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

    def do_activate(self):
        if self.notch is not None:
            self.notch.present()
            return

        self.theme = Theme(self.config, on_change=self._on_theme)
        self.media = Media(on_update=self._on_media)
        self.notch = Notch(self, self.config, self.media, lang())
        self.notch.present()
        self.notch.refresh()
        self.hold()

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self._on_sigusr1)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, self._on_sigusr2)

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
