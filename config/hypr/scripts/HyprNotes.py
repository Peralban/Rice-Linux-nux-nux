#!/usr/bin/env python3
"""HyprNotes — des notes, en fichiers texte (bilingue FR / EN).

Une barre latérale qui s'ouvre au bord de l'écran, une note à l'écran, et
un dossier de `.md` dans ~/.local/share/hyprnotes/ comme seule vérité.
Le notch lit le même dossier : une note épinglée s'y affiche et s'y coche.

Comme HyprWhale, il n'a pas de palette propre — il hérite de celle de GTK,
que matugen régénère à chaque changement de fond d'écran.

Signaux, comme le reste du dépôt :
  SIGUSR1  recharge la palette (matugen)
  SIGUSR2  ouvre / cache la fenêtre

La bascule du raccourci ne passe pas par `pkill`, contrairement au notch :
une ligne « pkill -f HyprNotes.py || HyprNotes.py » contient elle-même le
motif dans son repli, si bien que pkill signale le shell qui l'exécute, le
tue, et le repli n'est jamais atteint. On s'appuie plutôt sur l'unicité
d'instance de GApplication : relancer le script réveille l'instance en
place, et c'est `do_activate` qui bascule.
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
            # La fenêtre se cache au lieu de mourir : le raccourci la
            # rappelle instantanément, sans relire le dossier.
            self.hold()
            self.win.set_visible(True)
            self.win.present()
            return
        # Deuxième appui : le script relancé n'ouvre pas un second
        # processus, il réactive celui-ci. C'est donc ici qu'on bascule.
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
