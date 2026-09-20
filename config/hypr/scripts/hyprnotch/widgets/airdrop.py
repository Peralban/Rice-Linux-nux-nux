"""AirDrop: one switch, one state, and the shelf as the source of a send.

The notch's file shelf is already where you drop whatever you want to move
around. Sending to an iPhone is one more way out of it, no different in kind
from drag and drop.
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

        # Two pages rather than a floating sheet: picking a recipient replaces
        # the whole panel, the way the iOS share sheet takes the screen. A
        # popover would have left the state and the switch visible behind it,
        # which invites a click elsewhere in the middle of a send.
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(160)
        self.stack.add_named(self._build_main(), "main")
        self.stack.add_named(self._build_picker(), "pick")
        self.append(self.stack)

    def _build_main(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        # The logo large, as the focal point, the way Apple's AirDrop pane
        # does it: you come here to learn whether the machine is visible, and
        # that answer must read before any text. Controls go at the bottom.
        #
        # A theme icon rather than a font glyph: the concentric waves ARE the
        # AirDrop mark, and a missing Nerd Font codepoint would have rendered
        # as an empty box.
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

        # The control bar, at the bottom. The switch governs RECEIVING ONLY:
        # sending does not need us to be visible already, since `airdropd
        # send` brings the stack up itself when nothing is running. Greying
        # them together implied you had to switch on first.
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

        # A bare arrow, no label: the gesture is obvious and one more word
        # would have pushed the list further down.
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

    # --- lifecycle ------------------------------------------------------
    def set_live(self, live):
        if live and self.tick is None:
            self.tick = GLib.timeout_add(TICK_MS, self._on_tick)
            self.backend.refresh()
            # The shelf may have changed while we were looking elsewhere,
            # and the daemon's state will not have moved: without this render
            # the send button would stay greyed in front of a full shelf.
            self._render()
        elif not live and self.tick is not None:
            GLib.source_remove(self.tick)
            self.tick = None
            # Leaving the page while the picker is open would leave the
            # machine advertising over BLE with nothing saying so, and we
            # would come back later to a stale list.
            self._beacon_off()
            self.stack.set_visible_child_name("main")

    def _on_tick(self):
        if self.tick is None:
            return False
        self.backend.refresh()
        return True

    # --- interactions ---------------------------------------------------
    def _on_switch(self, _switch, wanted):
        # Only toggle when the user actually changed their mind: _render()
        # repositions the switch on every poll, and without this guard each
        # refresh would restart the daemon.
        if wanted != self.backend.is_on:
            self.backend.toggle()
            self._render()
        return True

    # --- the recipient picker --------------------------------------------
    # Browsing BEFORE anyone wants to send made no sense: the list was empty
    # most of the time, and "no device found" held the space permanently to
    # say nothing. So the browse starts on the Send click, and its results
    # appear in a sheet, the way the iOS share sheet does.

    def _on_send(self, _button):
        paths = list(self.shelf.paths) if self.shelf is not None else []
        if not paths:
            self.foot.set_text(self.s["empty"])
            return
        self._pending = paths
        self._open_picker()

    def _open_picker(self):
        # THE BLE WAKE FIRST. An iPhone only advertises itself as a receiver
        # once a Continuity advert has woken it, and the one `airdropd send`
        # registers through btmgmt does not reach the phone on this card.
        # Without this the browse finds nothing and the failure looks like a
        # phone problem. Measured: 29 s with no result on btmgmt alone, found
        # in 8 s with this advert.
        self.beacon.start()
        self.stack.set_visible_child_name("pick")

        # THE BROWSE NEEDS awdl0, not only the send. `opendrop find` opens the
        # interface, so with the stack down it fails instantly and the picker
        # shows "no device" without having looked at all. A send brings up its
        # own stack -- hence the switch being decoupled from the button but not
        # from discovery.
        if self.backend.is_on:
            self._fill_picker(busy=True)
            # 3 s before browsing, the same grace `airdropd send` gives the
            # phone: the advert has only just gone out and it needs that long
            # to start advertising back. Browsing immediately returns "no
            # device" when the phone was merely late, which reads as though
            # Everyone needed re-arming.
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
        # ~20 s to bring the radio up, per the upstream project. Leave some
        # headroom rather than give up on a slightly slow start.
        if self._wake_tries > 20:
            self._targets = []
            self._fill_picker()
            return False
        return True

    def _close_picker(self):
        # The advert only serves the browse and the handshake: leaving it
        # running afterwards would have the machine advertising indefinitely
        # with nothing in the interface saying so.
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
        # Bubbles rather than rows, like the iOS share sheet: a round avatar
        # with the name under it. One click sends -- no select-then-confirm,
        # a single gesture.
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
        # The transfer is started in the background: the advert is left alive
        # for the handshake, without which the phone can lose us between the
        # choice and the first packet.
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

        # The logo carries the state: off it stays grey, and it only takes on
        # a colour to flag something out of the ordinary.
        for css, want in (("nk-run", state in ("idle", "armed", "sending")),
                          ("nk-busy", state in ("waking", "switching", "unreachable")),
                          ("nk-down", state in ("error", "missing"))):
            if want:
                self.logo.add_css_class(css)
            else:
                self.logo.remove_css_class(css)

        # NOT `on and has`: the switch is the receiving one. A send brings up
        # its own stack if nothing is running, so greying it out while we are
        # off refused a perfectly valid action.
        has = bool(self.shelf.paths) if self.shelf is not None else False
        self.send.set_sensitive(state != "missing" and has)
