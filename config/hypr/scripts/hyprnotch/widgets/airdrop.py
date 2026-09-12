"""AirDrop : un interrupteur, un état, et l'étagère comme source d'envoi.

L'étagère à fichiers du notch est déjà l'endroit où l'on dépose ce qu'on
veut faire circuler. Envoyer vers un iPhone n'est qu'une sortie de plus,
au même titre que le glisser-déposer.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from ..integrations import airdrop as backend

TICK_MS = 2000

STRINGS = {
    "fr": {
        "title": "AIRDROP", "on": "Visible", "off": "Éteint",
        "send": "Envoyer l'étagère", "empty": "Étagère vide",
        "target": "Cible", "scan": "Chercher des appareils",
        "scanning": "Recherche…", "none": "Aucun appareil trouvé",
        "sent": "Envoi lancé", "recv": "Reçus dans ~/Downloads",
        "missing": "airdropd introuvable",
        "states": {
            "off": "Éteint", "waking": "Allumage…", "idle": "Visible",
            "armed": "Visible", "switching": "Bascule en 5 GHz…",
            "unreachable": "Visible, hors de portée", "sending": "Envoi…",
            "error": "Erreur", "missing": "Non installé",
        },
        "hint": {
            "off": "l'iPhone ne te voit pas",
            "waking": "la radio monte, ~20 s",
            "armed": "sur l'iPhone : Tout le monde, 10 min",
            "idle": "sur l'iPhone : Tout le monde, 10 min",
            "switching": "le GO a besoin du 5 GHz",
            "unreachable": "le téléphone est sur un autre canal",
            "sending": "transfert en cours",
            "error": "voir le journal du démon",
            "missing": "installe airdrop-mt7921",
        },
    },
    "en": {
        "title": "AIRDROP", "on": "Visible", "off": "Off",
        "send": "Send the shelf", "empty": "Shelf is empty",
        "target": "Target", "scan": "Look for devices",
        "scanning": "Searching…", "none": "No device found",
        "sent": "Send started", "recv": "Received in ~/Downloads",
        "missing": "airdropd not found",
        "states": {
            "off": "Off", "waking": "Waking…", "idle": "Visible",
            "armed": "Visible", "switching": "Moving to 5 GHz…",
            "unreachable": "Visible, out of reach", "sending": "Sending…",
            "error": "Error", "missing": "Not installed",
        },
        "hint": {
            "off": "the iPhone cannot see you",
            "waking": "radio coming up, ~20 s",
            "armed": "on the iPhone: Everyone, 10 min",
            "idle": "on the iPhone: Everyone, 10 min",
            "switching": "the GO needs 5 GHz",
            "unreachable": "the phone is on another channel",
            "sending": "transfer in progress",
            "error": "check the daemon log",
            "missing": "install airdrop-mt7921",
        },
    },
}


class AirDropWidget(Gtk.Box):
    def __init__(self, lang="fr", shelf=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.s = STRINGS.get(lang, STRINGS["fr"])
        self.shelf = shelf
        self.tick = None

        self.backend = backend.AirDrop()
        self.backend.connect(self._on_state)

        header = Gtk.Box(spacing=6)
        heading = Gtk.Label(label=self.s["title"], xalign=0, hexpand=True)
        heading.add_css_class("nk-sec")
        header.append(heading)
        self.append(header)

        # L'interrupteur, au centre : c'est la seule chose qu'on vient faire
        # ici la plupart du temps.
        centre = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                         valign=Gtk.Align.CENTER, vexpand=True,
                         halign=Gtk.Align.CENTER)

        self.switch = Gtk.Switch(halign=Gtk.Align.CENTER)
        self.switch.connect("state-set", self._on_switch)
        centre.append(self.switch)

        self.state = Gtk.Label(halign=Gtk.Align.CENTER)
        self.state.add_css_class("nk-stat-val")
        centre.append(self.state)

        self.hint = Gtk.Label(halign=Gtk.Align.CENTER, wrap=True, justify=Gtk.Justification.CENTER)
        self.hint.add_css_class("nk-meta")
        centre.append(self.hint)
        self.append(centre)

        # Choix de la cible. En « Tout le monde » tout appareil Apple a portee
        # repond, et le defaut du demon prend le premier arrive - donc au
        # hasard. La liste vient du dernier browse mDNS.
        pick = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        self.targets = Gtk.DropDown.new_from_strings([self.s["none"]])
        self.targets.set_sensitive(False)
        self.scan = Gtk.Button(tooltip_text=self.s["scan"], valign=Gtk.Align.CENTER)
        self.scan.set_child(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
        self.scan.add_css_class("nk-tab")
        self.scan.connect("clicked", self._on_scan)
        pick.append(self.targets)
        pick.append(self.scan)
        self.append(pick)
        self._targets = []

        self.send = Gtk.Button(label=self.s["send"], halign=Gtk.Align.CENTER)
        self.send.add_css_class("nk-btn")
        self.send.connect("clicked", self._on_send)
        self.append(self.send)

        self.foot = Gtk.Label(label=self.s["recv"], halign=Gtk.Align.CENTER)
        self.foot.add_css_class("nk-meta")
        self.append(self.foot)

        self._render()

    # --- cycle de vie ---------------------------------------------------
    def set_live(self, live):
        if live and self.tick is None:
            self.tick = GLib.timeout_add(TICK_MS, self._on_tick)
            self.backend.refresh()
            # L'étagère a pu changer pendant qu'on regardait ailleurs, et
            # l'état du démon, lui, n'aura pas bougé : sans ce rendu le
            # bouton d'envoi resterait grisé devant une étagère pleine.
            self._render()
        elif not live and self.tick is not None:
            GLib.source_remove(self.tick)
            self.tick = None

    def _on_tick(self):
        if self.tick is None:
            return False
        self.backend.refresh()
        return True

    # --- interactions ---------------------------------------------------
    def _on_switch(self, _switch, wanted):
        # On ne bascule que si l'utilisateur a vraiment changé d'avis :
        # _render() repositionne l'interrupteur à chaque sondage, et sans
        # cette garde chaque rafraîchissement relancerait le démon.
        if wanted != self.backend.is_on:
            self.backend.toggle()
            self._render()
        return True

    def _on_scan(self, _button):
        self.scan.set_sensitive(False)
        self.foot.set_text(self.s["scanning"])
        backend.discover(self._on_targets)

    def _on_targets(self, found):
        self.scan.set_sensitive(True)
        self._targets = found or []
        names = [n for _i, n in self._targets] or [self.s["none"]]
        self.targets.set_model(Gtk.StringList.new(names))
        self.targets.set_sensitive(bool(self._targets))
        self.foot.set_text(self.s["recv"] if self._targets else self.s["none"])
        self._render()

    def _chosen(self):
        i = self.targets.get_selected()
        if not self._targets or i == Gtk.INVALID_LIST_POSITION or i >= len(self._targets):
            return None
        return self._targets[i][0]

    def _on_send(self, _button):
        paths = list(self.shelf.paths) if self.shelf is not None else []
        if not paths:
            self.foot.set_text(self.s["empty"])
            return
        ok = self.backend.send(paths, receiver=self._chosen())
        self.foot.set_text(self.s["sent"] if ok else self.s["missing"])

    def _on_state(self, _state, _detail):
        self._render()

    def _render(self):
        state = self.backend.state
        on = self.backend.is_on

        self.switch.set_sensitive(state != "missing")
        if self.switch.get_active() != on:
            self.switch.handler_block_by_func(self._on_switch)
            self.switch.set_active(on)
            self.switch.handler_unblock_by_func(self._on_switch)

        self.state.set_text(self.s["states"].get(state, state))
        self.hint.set_text(self.s["hint"].get(state, ""))

        has = bool(self.shelf.paths) if self.shelf is not None else False
        self.send.set_sensitive(on and has)
