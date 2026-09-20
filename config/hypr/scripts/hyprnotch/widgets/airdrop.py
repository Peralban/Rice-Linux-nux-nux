"""AirDrop : un interrupteur, un état, et l'étagère comme source d'envoi.

L'étagère à fichiers du notch est déjà l'endroit où l'on dépose ce qu'on
veut faire circuler. Envoyer vers un iPhone n'est qu'une sortie de plus,
au même titre que le glisser-déposer.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from ..integrations import airdrop as backend
from ..integrations import ble

TICK_MS = 2000

STRINGS = {
    "fr": {
        "title": "AIRDROP", "on": "Visible", "off": "Éteint",
        "send": "Envoyer l'étagère", "empty": "Étagère vide",
        "pick": "Envoyer à…",
        "scanning": "Recherche d'appareils…", "none": "Aucun appareil trouvé",
        "waking": "Allumage de la radio…",
        "retry": "Chercher à nouveau",
        "sent": "AirDrop envoyé", "recv": "Reçus dans ~/Downloads",
        "missing": "airdropd introuvable",
        "states": {
            "off": "Éteint", "waking": "Allumage…", "idle": "Visible",
            "armed": "Visible", "switching": "Bascule en 5 GHz…",
            "unreachable": "Visible, hors de portée", "sending": "Envoi…",
            "error": "Erreur", "missing": "Non installé",
        },
        "hint": {
            "waking": "la radio monte, ~20 s",
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
        "pick": "Send to…",
        "scanning": "Looking for devices…", "none": "No device found",
        "waking": "Bringing the radio up…",
        "retry": "Look again",
        "sent": "AirDrop sent", "recv": "Received in ~/Downloads",
        "missing": "airdropd not found",
        "states": {
            "off": "Off", "waking": "Waking…", "idle": "Visible",
            "armed": "Visible", "switching": "Moving to 5 GHz…",
            "unreachable": "Visible, out of reach", "sending": "Sending…",
            "error": "Error", "missing": "Not installed",
        },
        "hint": {
            "waking": "radio coming up, ~20 s",
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
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.s = STRINGS.get(lang, STRINGS["fr"])
        self.shelf = shelf
        self.tick = None
        self._targets = []
        self._pending = []
        self.beacon = ble.Beacon()
        self._wake_tries = 0

        self.backend = backend.AirDrop()
        self.backend.connect(self._on_state)

        # Deux pages plutot qu'une feuille flottante : choisir un destinataire
        # remplace tout le panneau, comme le panneau de partage d'iOS prend
        # l'ecran. Une popover aurait laisse l'etat et l'interrupteur visibles
        # derriere, ce qui invite a cliquer ailleurs au milieu d'un envoi.
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(160)
        self.stack.add_named(self._build_main(), "main")
        self.stack.add_named(self._build_picker(), "pick")
        self.append(self.stack)

    def _build_main(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

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
        page.append(hero)

        page.append(self._sep())

        # Barre de commandes, en bas. L'interrupteur ne gouverne QUE la
        # reception : envoyer n'a pas besoin qu'on soit deja visible, puisque
        # `airdropd send` monte la pile lui-meme quand rien ne tourne. Les
        # griser ensemble laissait croire qu'il fallait s'allumer d'abord.
        bar = Gtk.Box(spacing=8)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.connect("state-set", self._on_switch)
        bar.append(self.switch)

        self.send = Gtk.Button(label=self.s["send"], valign=Gtk.Align.CENTER,
                               hexpand=True, halign=Gtk.Align.END)
        self.send.add_css_class("nk-act")
        self.send.connect("clicked", self._on_send)
        bar.append(self.send)
        page.append(bar)

        self.foot = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.foot.add_css_class("nk-meta")
        page.append(self.foot)
        return page

    def _build_picker(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Une fleche seule, sans libelle : le geste est evident et un mot de
        # plus aurait pousse la liste vers le bas.
        back = Gtk.Button(icon_name="go-previous-symbolic",
                          halign=Gtk.Align.START)
        back.add_css_class("nk-link")
        back.connect("clicked", lambda _b: self._close_picker())
        page.append(back)

        self.pick_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                 spacing=6, vexpand=True,
                                 valign=Gtk.Align.CENTER)
        page.append(self.pick_body)
        return page

    def _beacon_off(self):
        self.beacon.stop()
        return False

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
            # Quitter la page pendant que le selecteur est ouvert laisserait
            # la machine diffuser en BLE sans que rien ne le dise, et on
            # reviendrait plus tard sur une liste perimee.
            self._beacon_off()
            self.stack.set_visible_child_name("main")

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

    # --- le selecteur de destinataire ------------------------------------
    # Chercher AVANT de vouloir envoyer n'avait pas de sens : la liste etait
    # vide la plupart du temps, et « aucun appareil trouve » occupait la
    # place en permanence pour ne rien dire. La recherche part donc au clic
    # sur Envoyer, et ses resultats s'affichent dans une feuille, comme le
    # panneau de partage d'iOS.

    def _on_send(self, _button):
        paths = list(self.shelf.paths) if self.shelf is not None else []
        if not paths:
            self.foot.set_text(self.s["empty"])
            return
        self._pending = paths
        self._open_picker()

    def _open_picker(self):
        # LE SIGNAL BLE D'ABORD. Un iPhone ne s'annonce comme receveur qu'une
        # fois reveille par une annonce Continuity, et celle que `airdropd
        # send` enregistre par btmgmt n'atteint pas le telephone sur cette
        # carte. Sans ca la recherche ne trouve rien et l'echec ressemble a un
        # probleme de telephone. Mesure : 29 s sans resultat avec btmgmt seul,
        # trouve en 8 s avec cette annonce-ci.
        self.beacon.start()
        self.stack.set_visible_child_name("pick")

        # LA RECHERCHE A BESOIN D'awdl0, pas seulement l'envoi. `opendrop find`
        # ouvre l'interface, donc la pile eteinte il echoue instantanement et
        # le selecteur affiche « aucun appareil » sans avoir rien cherche.
        # L'envoi, lui, monte sa propre pile - d'ou l'interrupteur decouple du
        # bouton mais pas de la decouverte.
        if self.backend.is_on:
            self._fill_picker(busy=True)
            # 3 s avant de chercher, comme `airdropd send` en accorde au
            # telephone : l'annonce vient de partir et il lui faut ce temps
            # pour commencer a s'annoncer. Chercher tout de suite rend
            # « aucun appareil » alors qu'il etait simplement en retard, ce
            # qui donne l'impression qu'il faut rearmer Tout le monde.
            GLib.timeout_add_seconds(3, self._browse_now)
            return
        self._fill_picker(busy=True, label=self.s["waking"])
        self.backend.toggle()
        self._wake_tries = 0
        GLib.timeout_add_seconds(2, self._wait_awake)

    def _wait_awake(self):
        if self.stack.get_visible_child_name() != "pick":
            return False
        self._wake_tries += 1
        if self.backend.is_on and self.backend.state != "waking":
            self._fill_picker(busy=True)
            GLib.timeout_add_seconds(3, self._browse_now)
            return False
        # ~20 s pour monter la radio, d'apres le projet amont. On laisse une
        # marge plutot que d'abandonner sur un demarrage un peu lent.
        if self._wake_tries > 20:
            self._targets = []
            self._fill_picker()
            return False
        return True

    def _close_picker(self):
        # L'annonce ne sert qu'a la recherche et a la poignee de main : la
        # laisser tourner apres ferait diffuser la machine indefiniment sans
        # que rien dans l'interface ne le dise.
        self.beacon.stop()
        self.stack.set_visible_child_name("main")
        self._pending = []

    def _clear_picker(self):
        while (child := self.pick_body.get_first_child()) is not None:
            self.pick_body.remove(child)

    def _browse_now(self):
        if self.stack.get_visible_child_name() == "pick":
            backend.discover(self._on_targets)
        return False

    def _fill_picker(self, busy=False, label=None):
        self._clear_picker()
        if busy:
            row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
            spinner = Gtk.Spinner()
            spinner.start()
            row.append(spinner)
            row.append(Gtk.Label(label=label or self.s["scanning"]))
            self.pick_body.append(row)
            return
        if not self._targets:
            empty = Gtk.Label(label=self.s["none"], wrap=True,
                              justify=Gtk.Justification.CENTER)
            empty.add_css_class("nk-meta")
            self.pick_body.append(empty)
            again = Gtk.Button(label=self.s["retry"], halign=Gtk.Align.CENTER)
            again.add_css_class("nk-link")
            again.connect("clicked", lambda _b: self._open_picker())
            self.pick_body.append(again)
            return
        # Des bulles plutot que des lignes, comme le panneau de partage d'iOS :
        # un avatar rond, le nom dessous. Un clic envoie - pas de selection
        # puis validation, un seul geste.
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                           homogeneous=True, column_spacing=4,
                           row_spacing=8, min_children_per_line=2,
                           max_children_per_line=3,
                           halign=Gtk.Align.CENTER)
        for ident, name in self._targets:
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                           halign=Gtk.Align.CENTER)
            bubble = Gtk.Button(halign=Gtk.Align.CENTER)
            bubble.add_css_class("nk-bubble")
            icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
            icon.set_pixel_size(28)
            bubble.set_child(icon)
            bubble.connect("clicked", self._on_pick, ident)
            cell.append(bubble)
            label = Gtk.Label(label=name, max_width_chars=11, wrap=True,
                              justify=Gtk.Justification.CENTER, lines=2,
                              ellipsize=Pango.EllipsizeMode.END)
            label.add_css_class("nk-meta")
            cell.append(label)
            flow.append(cell)
        self.pick_body.append(flow)

    def _on_targets(self, found):
        self._targets = found or []
        if self.stack.get_visible_child_name() != "pick":
            return
        self._fill_picker()

    def _on_pick(self, _button, ident):
        paths = self._pending or (
            list(self.shelf.paths) if self.shelf is not None else [])
        self.stack.set_visible_child_name("main")
        if not paths:
            self.foot.set_text(self.s["empty"])
            return
        ok = self.backend.send(paths, receiver=ident)
        self.foot.set_text(self.s["sent"] if ok else self.s["missing"])
        self._pending = []
        # Le transfert est lance en arriere-plan : on laisse l'annonce vivre
        # le temps de la poignee de main, sans quoi le telephone peut nous
        # perdre entre le choix et le premier paquet.
        GLib.timeout_add_seconds(20, self._beacon_off)

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

        # PAS `on and has` : l'interrupteur est celui de la reception. Un
        # envoi monte sa propre pile si rien ne tourne, donc le griser quand
        # on est eteint refusait une action parfaitement valide.
        has = bool(self.shelf.paths) if self.shelf is not None else False
        self.send.set_sensitive(state != "missing" and has)
