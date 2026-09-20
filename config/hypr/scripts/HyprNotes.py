#!/usr/bin/env python3
"""HyprNotes -- notes, as text files (bilingual FR / EN).

A sidebar that opens at the edge of the screen, one note on screen, and a
directory of `.md` files in ~/.local/share/hyprnotes/ as the only truth. The
notch reads the same directory: a pinned note is shown and ticked there.

Like HyprWhale, it has no palette of its own -- it inherits GTK's, which
matugen regenerates on every wallpaper change.

Signals, as elsewhere in this repository:
  SIGUSR1  reload the palette (matugen)
  SIGUSR2  show / hide the window

The shortcut's toggle does not go through `pkill`, unlike the notch's: a line
like "pkill -f HyprNotes.py || HyprNotes.py" contains the pattern inside its
own fallback, so pkill signals the shell running it, kills it, and the
fallback is never reached. We rely on GApplication's single-instance
behaviour instead: relaunching the script wakes the instance already there,
and `do_activate` is what toggles.
"""

import os
import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hyprnotes.window import NotesWindow  # noqa: E402

APP_ID = "dev.local.HyprNotes"


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.win = None

    def do_activate(self):
        if self.win is None:
            self.win = NotesWindow(self)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self._theme)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, self._toggle)
            # The window hides instead of dying: the shortcut brings it back
            # instantly, without re-reading the directory.
            self.hold()
            self.win.set_visible(True)
            self.win.present()
            return
        # Second press: the relaunched script does not open a second process,
        # it reactivates this one. So this is where the toggle happens.
        self.win.toggle_window()

    def _theme(self):
        if self.win:
            self.win.reload_theme()
        return True

    def _toggle(self):
        if self.win:
            self.win.toggle_window()
        return True


if __name__ == "__main__":
    App().run(None)
