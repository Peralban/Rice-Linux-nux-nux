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
        "scan": "Chercher",
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
        "scan": "Look",
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
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.s = STRINGS.get(lang, STRINGS["fr"])
        self.shelf = shelf
        self.tick = None

        self.backend = backend.AirDrop()
        self.backend.connect(self._on_state)

        # Le logo en grand comme point focal, a la maniere du panneau AirDrop
        # d'Apple : on vient ici pour savoir si la machine est visible, et la
        # reponse doit se lire avant tout texte. Les commandes vont en bas.
        #
        # Icone du theme plutot qu'un glyphe de police : les ondes
        # concentriques SONT la marque AirDrop, et un codepoint Nerd Font
        # absent se serait affiche en carre vide.
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                       valign=Gtk.Align.CENTER, vexpand=True,
                       halign=Gtk.Align.CENTER)

        self.logo = Gtk.Image.new_from_icon_name("network-wireless-symbolic")
        self.logo.set_pixel_size(40)
        self.logo.add_css_class("nk-logo")
        hero.append(self.logo)

        name = Gtk.Label(label="AirDrop")
        name.add_css_class("nk-name")
        hero.append(name)

        self.state = Gtk.Label()
        self.state.add_css_class("nk-state")
        hero.append(self.state)

        self.hint = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.hint.add_css_class("nk-meta")
        hero.append(self.hint)
        self.append(hero)

        # Les cibles n'apparaissent que s'il y en a : une liste annoncant
        # « aucun appareil » prenait la place pour ne rien dire.
        self.targets = Gtk.DropDown.new_from_strings([self.s["none"]])
        self.targets.add_css_class("nk-pick")
        self.targets.set_visible(False)
        self.append(self.targets)
        self._targets = []

        self.append(self._sep())

        # Barre de commandes, en bas : l'interrupteur porte l'etat, les deux
        # actions d'envoi suivent.
        bar = Gtk.Box(spacing=8)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.connect("state-set", self._on_switch)
        bar.append(self.switch)

        self.scan = Gtk.Button(label=self.s["scan"], valign=Gtk.Align.CENTER,
                               hexpand=True, halign=Gtk.Align.END)
        self.scan.add_css_class("nk-link")
        self.scan.connect("clicked", self._on_scan)
        bar.append(self.scan)

        self.send = Gtk.Button(label=self.s["send"], valign=Gtk.Align.CENTER)
        self.send.add_css_class("nk-act")
        self.send.connect("clicked", self._on_send)
        bar.append(self.send)
        self.append(bar)

        self.foot = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.foot.add_css_class("nk-meta")
        self.append(self.foot)

    @staticmethod
    def _sep():
        line = Gtk.Box()
        line.add_css_class("nk-sep")
        line.set_size_request(-1, 1)
        return line

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
        self.foot.set_text("" if self._targets else self.s["none"])
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

        # C'est le logo qui porte l'etat : eteint il reste gris, et il ne
        # prend une couleur que pour signaler un ecart.
        for css, want in (("nk-run", state in ("idle", "armed", "sending")),
                          ("nk-busy", state in ("waking", "switching", "unreachable")),
                          ("nk-down", state in ("error", "missing"))):
            if want:
                self.logo.add_css_class(css)
            else:
                self.logo.remove_css_class(css)

        has = bool(self.shelf.paths) if self.shelf is not None else False
        self.send.set_sensitive(on and has)
        self.scan.set_sensitive(on)
        self.targets.set_visible(bool(self._targets))
