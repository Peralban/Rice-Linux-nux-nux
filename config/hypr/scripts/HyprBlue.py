#!/usr/bin/env python3
"""HyprBlue -- the Bluetooth manager (bilingual FR / EN).

Replaces blueman-manager, with the desktop's own look: power, your devices
(connect, disconnect, trust, rename, forget, battery), and a search for new
ones to pair.

It talks to BlueZ directly over D-Bus rather than through bluetoothctl:
BlueZ announces every change (a device appearing, connecting, its battery),
so the window follows the radio instead of polling it.

Two details worth knowing:

  * "Off" can be an rfkill soft block, which BlueZ reports as PowerState
    "off-blocked"; setting Powered then fails with org.bluez.Error.Blocked.
    Turning on lifts the block first -- /dev/rfkill is the session user's,
    no sudo involved.
  * Pairing may need a code confirmed or typed. That is an Agent1 object on
    the bus: this app registers one, and BlueZ hands it the pairings this app
    starts. It becomes the *default* agent (the one asked when a phone pairs
    from its side) only while blueman's applet is not running, so as not to
    take that role from it behind its back.

Like the other panels it has no palette of its own: it inherits GTK's, which
matugen regenerates on every wallpaper change. SIGUSR1 reloads the theme.
"""

import os
import signal
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

APP_ID = "dev.local.HyprBlue"
LANG_FILE = os.path.expanduser("~/.config/hypr/scripts/.hyprsettings-lang")
BLUEZ = "org.bluez"
AGENT_PATH = "/dev/local/HyprBlue/agent"
SEARCH_SECONDS = 45

G_BT = "\U000f00af"
G_BT_OFF = "\U000f00b2"
G_HEAD = "\U000f02cb"
G_HEADSET = "\U000f02ce"
G_SPEAKER = "\U000f04c3"
G_PHONE = "\U000f011c"
G_LAPTOP = "\U000f0322"
G_MOUSE = "\U000f037d"
G_KEYBOARD = "\U000f030c"
G_GAMEPAD = "\U000f02b4"
G_WATCH = "\U000f0598"

T = {
    "fr": {
        "title": "Bluetooth",
        "search": "Rechercher", "searching": "Recherche…",
        "mine": "Mes appareils", "nearby": "À proximité",
        "none_mine": "Aucun appareil appairé",
        "none_mine_sub": "Lance une recherche pour en ajouter un",
        "none_near": "Rien pour l'instant",
        "none_near_sub": "Mets l'appareil en mode appairage",
        "hidden": "+ {n} sans nom",
        "connected": "Connecté", "disconnected": "Déconnecté",
        "connecting": "Connexion…", "disconnecting": "Déconnexion…", "pairing": "Appairage…",
        "connect": "Connecter", "disconnect": "Déconnecter", "pair": "Appairer",
        "trust": "Reconnexion automatique", "rename": "Renommer", "forget": "Oublier",
        "forget_q": "Oublier {name} ?",
        "forget_body": "Il faudra l'appairer à nouveau pour s'en servir.",
        "rename_q": "Renommer l'appareil",
        "cancel": "Annuler", "ok": "Valider", "confirm": "Confirmer", "reject": "Refuser",
        "off": "Bluetooth éteint", "off_sub": "Allume-le pour retrouver tes appareils",
        "blocked_sub": "Coupé par le mode avion : l'allumer le lève aussi",
        "turn_on": "Allumer",
        "no_adapter": "Aucun adaptateur Bluetooth",
        "no_adapter_sub": "BlueZ ne voit pas de puce Bluetooth sur cette machine",
        "visible": "Visible par les autres appareils",
        "visible_sub": "Le temps d'appairer un téléphone, par exemple",
        "signal_strong": "signal fort", "signal_mid": "signal moyen", "signal_weak": "signal faible",
        "code_q": "Code d'appairage",
        "code_confirm": "Vérifie que {name} affiche le code\n\n{code}",
        "code_show": "Tape ce code sur {name} :\n\n{code}",
        "pin_ask": "Saisis le code PIN de {name}",
        "pass_ask": "Saisis le code affiché par {name}",
        "auth_ask": "{name} veut se connecter. L'autoriser ?",
        "e_unreachable": "{name} est injoignable : allumé et à portée ?",
        "e_auth": "Appairage refusé par {name}",
        "e_busy": "Une opération est déjà en cours",
        "e_blocked": "Le Bluetooth est bloqué (rfkill)",
        "e_other": "{name} : {err}",
        "paired": "{name} est appairé",
    },
    "en": {
        "title": "Bluetooth",
        "search": "Search", "searching": "Searching…",
        "mine": "My devices", "nearby": "Nearby",
        "none_mine": "No paired device",
        "none_mine_sub": "Start a search to add one",
        "none_near": "Nothing yet",
        "none_near_sub": "Put the device in pairing mode",
        "hidden": "+ {n} unnamed",
        "connected": "Connected", "disconnected": "Disconnected",
        "connecting": "Connecting…", "disconnecting": "Disconnecting…", "pairing": "Pairing…",
        "connect": "Connect", "disconnect": "Disconnect", "pair": "Pair",
        "trust": "Reconnect automatically", "rename": "Rename", "forget": "Forget",
        "forget_q": "Forget {name}?",
        "forget_body": "It will have to be paired again to be used.",
        "rename_q": "Rename the device",
        "cancel": "Cancel", "ok": "OK", "confirm": "Confirm", "reject": "Reject",
        "off": "Bluetooth is off", "off_sub": "Turn it on to find your devices",
        "blocked_sub": "Off through airplane mode: turning it on lifts that too",
        "turn_on": "Turn on",
        "no_adapter": "No Bluetooth adapter",
        "no_adapter_sub": "BlueZ sees no Bluetooth chip on this machine",
        "visible": "Visible to other devices",
        "visible_sub": "Long enough to pair a phone, for instance",
        "signal_strong": "strong signal", "signal_mid": "fair signal", "signal_weak": "weak signal",
        "code_q": "Pairing code",
        "code_confirm": "Check that {name} shows the code\n\n{code}",
        "code_show": "Type this code on {name}:\n\n{code}",
        "pin_ask": "Enter the PIN of {name}",
        "pass_ask": "Enter the code shown by {name}",
        "auth_ask": "{name} wants to connect. Allow it?",
        "e_unreachable": "{name} cannot be reached: is it on and in range?",
        "e_auth": "{name} refused the pairing",
        "e_busy": "Something is already in progress",
        "e_blocked": "Bluetooth is blocked (rfkill)",
        "e_other": "{name}: {err}",
        "paired": "{name} is paired",
    },
}

AGENT_XML = """
<node>
  <interface name="org.bluez.Agent1">
    <method name="Release"/>
    <method name="RequestPinCode">
      <arg type="o" direction="in"/><arg type="s" direction="out"/>
    </method>
    <method name="DisplayPinCode">
      <arg type="o" direction="in"/><arg type="s" direction="in"/>
    </method>
    <method name="RequestPasskey">
      <arg type="o" direction="in"/><arg type="u" direction="out"/>
    </method>
    <method name="DisplayPasskey">
      <arg type="o" direction="in"/><arg type="u" direction="in"/><arg type="q" direction="in"/>
    </method>
    <method name="RequestConfirmation">
      <arg type="o" direction="in"/><arg type="u" direction="in"/>
    </method>
    <method name="RequestAuthorization">
      <arg type="o" direction="in"/>
    </method>
    <method name="AuthorizeService">
      <arg type="o" direction="in"/><arg type="s" direction="in"/>
    </method>
    <method name="Cancel"/>
  </interface>
</node>
"""

CSS = b"""
window.hb-root, window.hb-root.background { background: alpha(@window_bg_color, 0.97); }
.hb-root, .hb-root button, .hb-root label {
  font-family: "JetBrainsMono Nerd Font Propo", "JetBrains Mono", monospace;
  font-size: 12px;
}
.hb-root headerbar { background: transparent; box-shadow: none; }
.hb-root .hb-sec { font-size: 10px; letter-spacing: 1.6px; opacity: 0.65; }
.hb-root .hb-name { font-weight: 700; font-size: 12.5px; }
.hb-root .hb-meta { font-size: 11px; opacity: 0.66; }
.hb-root .hb-icon { font-size: 19px; min-width: 26px; }
.hb-root .hb-big { font-size: 40px; opacity: 0.5; }
.hb-root .hb-live { color: @accent_color; opacity: 1; }
.hb-card {
  padding: 9px 12px; border-radius: 10px;
  background: alpha(currentColor, 0.045);
  border: 1px solid alpha(currentColor, 0.08);
}
.hb-card.hb-on {
  background: alpha(@accent_color, 0.08);
  border-color: alpha(@accent_color, 0.25);
}
.hb-on .hb-icon { color: @accent_color; }
.hb-root button.hb-act, .hb-root menubutton.hb-act > button {
  min-height: 24px; padding: 0 10px; font-size: 11px; border-radius: 7px;
  background: none; border: 1px solid alpha(currentColor, 0.28); box-shadow: none;
}
/* the menu button is a box around a button: the frame belongs on the inner one */
.hb-root menubutton.hb-act > button { min-width: 0; padding: 0 8px; }
.hb-root button.hb-act:hover, .hb-root menubutton.hb-act > button:hover,
.hb-root menubutton.hb-act > button:checked { background: alpha(@accent_color, 0.16); }
.hb-root button.hb-go { border-color: alpha(@accent_color, 0.55); color: @accent_color; }
.hb-root button.hb-item {
  min-height: 28px; padding: 0 10px; background: none; border: none; box-shadow: none;
}
.hb-root button.hb-item:hover { background: alpha(@accent_color, 0.14); }
.hb-root button.hb-danger { color: #f2777a; }
.hb-empty { margin: 18px 12px; }
"""


def lang():
    try:
        with open(LANG_FILE, encoding="utf-8") as fh:
            v = fh.read().strip()
            if v in T:
                return v
    except OSError:
        pass
    return "fr"


def glyph(icon):
    icon = icon or ""
    for key, g in (("headset", G_HEADSET), ("headphone", G_HEAD), ("audio-card", G_HEAD),
                   ("speaker", G_SPEAKER), ("phone", G_PHONE), ("computer", G_LAPTOP),
                   ("mouse", G_MOUSE), ("keyboard", G_KEYBOARD), ("gaming", G_GAMEPAD),
                   ("watch", G_WATCH), ("audio", G_SPEAKER)):
        if key in icon:
            return g
    return G_BT


def blueman_running():
    try:
        return subprocess.run(["pgrep", "-f", "blueman-applet"], capture_output=True).returncode == 0
    except OSError:
        return False


class Device:
    def __init__(self, path, props, battery):
        self.path = path
        self.address = props.get("Address", "")
        self.name = props.get("Alias") or props.get("Name") or ""
        # BlueZ fills Alias with the address when a device announces no name;
        # Name is there only when it does.
        self.named = bool(props.get("Name"))
        self.paired = bool(props.get("Paired"))
        self.trusted = bool(props.get("Trusted"))
        self.connected = bool(props.get("Connected"))
        self.icon = props.get("Icon", "")
        self.rssi = props.get("RSSI")
        self.battery = battery

    def key(self):
        return (self.path, self.name, self.paired, self.trusted, self.connected, self.icon,
                self.battery, None if self.rssi is None else self.rssi // 12)


class Blue(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, default_width=520, default_height=640)
        self.s = T[lang()]
        self.set_title("HyprBlue")
        self.add_css_class("hb-root")

        self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        self.adapter = None          # (path, props)
        self.devices = []
        self.shape = None
        self.busy = {}               # device path -> "connecting" / "pairing" / ...
        self.search_timer = None
        self._refresh_id = None
        self._quiet = False
        self.agent_id = None
        self.agent_dialog = None

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        header = Adw.HeaderBar()
        # the window title stays "HyprBlue" for Hyprland's rules; people read this
        header.set_title_widget(Adw.WindowTitle(title=self.s["title"]))
        self.power = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.power.connect("notify::active", self._on_power)
        header.pack_end(self.power)
        self.search_btn = Gtk.Button()
        self.search_btn.add_css_class("hb-act")
        self.search_btn.connect("clicked", lambda _b: self._toggle_search())
        header.pack_start(self.search_btn)

        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        self.body.set_margin_start(14); self.body.set_margin_end(14)
        self.body.set_margin_top(4); self.body.set_margin_bottom(14)
        scroller = Gtk.ScrolledWindow(child=self.body, vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.toasts = Adw.ToastOverlay(child=scroller)
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self.toasts)
        self.set_content(view)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.connect("close-request", self._on_close)

        # Everything BlueZ says, debounced into one re-read.
        self.sub = self.bus.signal_subscribe(BLUEZ, None, None, None, None,
                                             Gio.DBusSignalFlags.NONE, self._on_signal)
        self._register_agent()
        self.refresh()

    def _on_key(self, _c, keyval, _kc, _st):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return Gdk.EVENT_STOP
        return Gdk.EVENT_PROPAGATE

    def _on_close(self, *_):
        if self.adapter and self.adapter[1].get("Discovering"):
            self._call(self.adapter[0], "org.bluez.Adapter1", "StopDiscovery")
        self.bus.signal_unsubscribe(self.sub)
        if self.agent_id:
            self._call("/org/bluez", "org.bluez.AgentManager1", "UnregisterAgent",
                       GLib.Variant("(o)", (AGENT_PATH,)))
            self.bus.unregister_object(self.agent_id)
        return False

    # -- D-Bus -------------------------------------------------------------

    def _call(self, path, iface, method, params=None, done=None, timeout=-1):
        """Asynchronous: Connect and Pair take seconds, the window must not."""
        def finish(bus, result):
            try:
                bus.call_finish(result)
                error = None
            except GLib.Error as e:
                error = e
            if done:
                done(error)
        self.bus.call(BLUEZ, path, iface, method, params, None,
                      Gio.DBusCallFlags.NONE, timeout, None, finish)

    def _set(self, path, iface, prop, value, done=None):
        self._call(path, "org.freedesktop.DBus.Properties", "Set",
                   GLib.Variant("(ssv)", (iface, prop, value)), done)

    def _on_signal(self, *_args):
        if self._refresh_id is None:
            self._refresh_id = GLib.timeout_add(120, self._refreshed)

    def _refreshed(self):
        self._refresh_id = None
        self.refresh()
        return GLib.SOURCE_REMOVE

    def refresh(self):
        try:
            reply = self.bus.call_sync(BLUEZ, "/", "org.freedesktop.DBus.ObjectManager",
                                       "GetManagedObjects", None, None,
                                       Gio.DBusCallFlags.NONE, 3000, None)
            objects = reply.unpack()[0]
        except GLib.Error:
            objects = {}
        self.adapter = None
        devices = []
        for path, ifaces in sorted(objects.items()):
            if "org.bluez.Adapter1" in ifaces and self.adapter is None:
                self.adapter = (path, ifaces["org.bluez.Adapter1"])
            if "org.bluez.Device1" in ifaces:
                battery = ifaces.get("org.bluez.Battery1", {}).get("Percentage")
                devices.append(Device(path, ifaces["org.bluez.Device1"], battery))
        if self.adapter:
            devices = [d for d in devices if d.path.startswith(self.adapter[0] + "/")]
        self.devices = devices
        shape = (None if not self.adapter else
                 (self.adapter[1].get("Powered"), self.adapter[1].get("PowerState"),
                  self.adapter[1].get("Discovering"), self.adapter[1].get("Discoverable")),
                 tuple(d.key() for d in devices), tuple(sorted(self.busy.items())))
        if shape != self.shape:
            self.shape = shape
            self._render()
        return GLib.SOURCE_REMOVE

    # -- rendering ---------------------------------------------------------

    @staticmethod
    def _label(text, *classes, wrap=False, ellipsize=False, xalign=0):
        lbl = Gtk.Label(label=text, xalign=xalign)
        for c in classes:
            lbl.add_css_class(c)
        if wrap:
            lbl.set_wrap(True)
            lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if ellipsize:
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
        return lbl

    def _render(self):
        while (child := self.body.get_first_child()) is not None:
            self.body.remove(child)

        powered = bool(self.adapter and self.adapter[1].get("Powered"))
        discovering = bool(self.adapter and self.adapter[1].get("Discovering"))
        self._quiet = True
        self.power.set_active(powered)
        self.power.set_sensitive(self.adapter is not None)
        self._quiet = False
        self.search_btn.set_visible(powered)
        self.search_btn.set_label(self.s["searching"] if discovering else self.s["search"])
        if discovering:
            self.search_btn.add_css_class("hb-go")
        else:
            self.search_btn.remove_css_class("hb-go")

        if self.adapter is None:
            self.body.append(self._big(G_BT_OFF, self.s["no_adapter"], self.s["no_adapter_sub"]))
            return
        if not powered:
            blocked = self.adapter[1].get("PowerState") == "off-blocked"
            box = self._big(G_BT_OFF, self.s["off"],
                            self.s["blocked_sub"] if blocked else self.s["off_sub"])
            on = Gtk.Button(label=self.s["turn_on"], halign=Gtk.Align.CENTER)
            on.add_css_class("hb-act"); on.add_css_class("hb-go")
            on.set_margin_top(10)
            on.connect("clicked", lambda _b: self.power.set_active(True))
            box.append(on)
            self.body.append(box)
            return

        mine = sorted((d for d in self.devices if d.paired),
                      key=lambda d: (not d.connected, d.name.lower()))
        self.body.append(self._section(self.s["mine"]))
        if mine:
            for d in mine:
                self.body.append(self._card(d))
        else:
            self.body.append(self._empty(self.s["none_mine"], self.s["none_mine_sub"]))

        if discovering or any(not d.paired and d.path in self.busy for d in self.devices):
            near = [d for d in self.devices if not d.paired]
            named = sorted((d for d in near if d.named),
                           key=lambda d: -(d.rssi if d.rssi is not None else -999))
            self.body.append(self._section(self.s["nearby"]))
            if named:
                for d in named:
                    self.body.append(self._card(d))
            else:
                self.body.append(self._empty(self.s["none_near"], self.s["none_near_sub"]))
            hidden = len(near) - len(named)
            if hidden:
                self.body.append(self._label(self.s["hidden"].format(n=hidden), "hb-meta", xalign=0.5))

        self.body.append(self._section(""))
        row = Gtk.Box(spacing=12)
        row.add_css_class("hb-card")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        texts.append(self._label(self.s["visible"], "hb-name"))
        texts.append(self._label(self.s["visible_sub"], "hb-meta", wrap=True))
        row.append(texts)
        visible = Gtk.Switch(valign=Gtk.Align.CENTER, active=bool(self.adapter[1].get("Discoverable")))
        visible.connect("notify::active", lambda w, _p: self._set(
            self.adapter[0], "org.bluez.Adapter1", "Discoverable", GLib.Variant("b", w.get_active())))
        row.append(visible)
        self.body.append(row)

    def _section(self, title):
        lbl = self._label(title.upper(), "hb-sec")
        lbl.set_margin_top(10); lbl.set_margin_start(2)
        return lbl

    def _empty(self, title, sub):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.add_css_class("hb-empty")
        box.append(self._label(title, "hb-name", xalign=0.5))
        box.append(self._label(sub, "hb-meta", xalign=0.5, wrap=True))
        return box

    def _big(self, icon, title, sub):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, vexpand=True,
                      valign=Gtk.Align.CENTER)
        box.set_margin_top(80)
        box.append(self._label(icon, "hb-big", xalign=0.5))
        box.append(self._label(title, "hb-name", xalign=0.5))
        box.append(self._label(sub, "hb-meta", xalign=0.5, wrap=True))
        return box

    def _meta(self, d):
        state = self.busy.get(d.path)
        if state:
            return self.s[state]
        if not d.paired:
            if d.rssi is None:
                return d.address
            strength = ("signal_strong" if d.rssi > -60 else
                        "signal_mid" if d.rssi > -78 else "signal_weak")
            return self.s[strength]
        bits = [self.s["connected"] if d.connected else self.s["disconnected"]]
        if d.battery is not None:
            bits.append(f"{d.battery} %")
        return "  ·  ".join(bits)

    def _card(self, d):
        card = Gtk.Box(spacing=10)
        card.add_css_class("hb-card")
        if d.connected:
            card.add_css_class("hb-on")
        card.append(self._label(glyph(d.icon), "hb-icon"))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        texts.append(self._label(d.name or d.address, "hb-name", ellipsize=True))
        texts.append(self._label(self._meta(d), "hb-meta", ellipsize=True))
        card.append(texts)

        busy = d.path in self.busy
        if not d.paired:
            b = Gtk.Button(label=self.s["pair"], valign=Gtk.Align.CENTER)
            b.add_css_class("hb-go")
            b.connect("clicked", lambda _b: self._pair(d))
        elif d.connected:
            b = Gtk.Button(label=self.s["disconnect"], valign=Gtk.Align.CENTER)
            b.connect("clicked", lambda _b: self._device(d, "Disconnect", "disconnecting"))
        else:
            b = Gtk.Button(label=self.s["connect"], valign=Gtk.Align.CENTER)
            b.add_css_class("hb-go")
            b.connect("clicked", lambda _b: self._device(d, "Connect", "connecting"))
        b.add_css_class("hb-act")
        b.set_sensitive(not busy)
        card.append(b)
        if d.paired:
            card.append(self._menu(d))
        return card

    def _menu(self, d):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.set_margin_top(5); box.set_margin_bottom(5)
        box.set_margin_start(5); box.set_margin_end(5)

        trust = Gtk.CheckButton(label=self.s["trust"], active=d.trusted)
        trust.set_margin_start(6); trust.set_margin_end(6)
        trust.connect("toggled", lambda w: self._set(
            d.path, "org.bluez.Device1", "Trusted", GLib.Variant("b", w.get_active())))
        box.append(trust)

        def item(label, cb, danger=False):
            b = Gtk.Button(label=label)
            b.add_css_class("hb-item")
            if danger:
                b.add_css_class("hb-danger")
            b.get_child().set_xalign(0.0)
            b.connect("clicked", lambda _x: (pop.popdown(), cb()))
            box.append(b)
        item(self.s["rename"], lambda: self._rename(d))
        item(self.s["forget"], lambda: self._forget(d), danger=True)

        pop.set_child(box)
        btn = Gtk.MenuButton(valign=Gtk.Align.CENTER)
        btn.set_child(Gtk.Label(label="⋯"))
        btn.add_css_class("hb-act")
        btn.set_popover(pop)
        return btn

    # -- actions -----------------------------------------------------------

    def _error(self, d, error):
        text = error.message if error else ""
        if any(k in text for k in ("page-timeout", "Page Timeout", "Host is down", "not available",
                                   "profile-unavailable", "No route")):
            msg = self.s["e_unreachable"]
        elif any(k in text for k in ("Authentication", "Rejected", "Canceled")):
            msg = self.s["e_auth"]
        elif "InProgress" in text or "in progress" in text:
            msg = self.s["e_busy"]
        elif "Blocked" in text:
            msg = self.s["e_blocked"]
        else:
            msg = None
        name = (d.name or d.address) if d else ""
        if msg is None:
            # the raw D-Bus text, which may hold braces: never through format()
            short = text.split(": ")[-1] if text else "?"
            title = self.s["e_other"].replace("{name}", name).replace("{err}", short)
        else:
            title = msg.format(name=name)
        self.toasts.add_toast(Adw.Toast(title=title, timeout=5))

    def _device(self, d, method, state):
        self.busy[d.path] = state
        self.refresh()

        def done(error):
            self.busy.pop(d.path, None)
            if error and "AlreadyConnected" not in error.message and "NotConnected" not in error.message:
                self._error(d, error)
            self.refresh()
        self._call(d.path, "org.bluez.Device1", method, done=done, timeout=30000)

    def _pair(self, d):
        self.busy[d.path] = "pairing"
        self.refresh()

        def paired(error):
            if error and "AlreadyExists" not in error.message:
                self.busy.pop(d.path, None)
                self._error(d, error)
                self.refresh()
                return
            # Trusted: BlueZ reconnects it by itself from now on.
            self._set(d.path, "org.bluez.Device1", "Trusted", GLib.Variant("b", True))
            self.toasts.add_toast(Adw.Toast(title=self.s["paired"].format(name=d.name or d.address),
                                            timeout=3))
            self.busy[d.path] = "connecting"
            self.refresh()

            def connected(err):
                self.busy.pop(d.path, None)
                if err and "AlreadyConnected" not in err.message:
                    self._error(d, err)
                self.refresh()
            self._call(d.path, "org.bluez.Device1", "Connect", done=connected, timeout=30000)
        self._call(d.path, "org.bluez.Device1", "Pair", done=paired, timeout=90000)

    def _rename(self, d):
        dialog = Adw.AlertDialog(heading=self.s["rename_q"])
        entry = Gtk.Entry(text=d.name)
        entry.set_activates_default(True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", self.s["cancel"])
        dialog.add_response("ok", self.s["ok"])
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("ok")

        def answered(_d, response):
            name = entry.get_text().strip()
            if response == "ok" and name and name != d.name:
                self._set(d.path, "org.bluez.Device1", "Alias", GLib.Variant("s", name))
        dialog.connect("response", answered)
        dialog.present(self)

    def _forget(self, d):
        dialog = Adw.AlertDialog(heading=self.s["forget_q"].format(name=d.name or d.address),
                                 body=self.s["forget_body"])
        dialog.add_response("cancel", self.s["cancel"])
        dialog.add_response("forget", self.s["forget"])
        dialog.set_response_appearance("forget", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")

        def answered(_d, response):
            if response == "forget" and self.adapter:
                self._call(self.adapter[0], "org.bluez.Adapter1", "RemoveDevice",
                           GLib.Variant("(o)", (d.path,)),
                           done=lambda e: self._error(d, e) if e else None)
        dialog.connect("response", answered)
        dialog.present(self)

    def _on_power(self, switch, _pspec):
        if self._quiet or self.adapter is None:
            return
        want = switch.get_active()
        if want and self.adapter[1].get("PowerState") == "off-blocked":
            # The block first: Powered=true on a blocked adapter is refused.
            subprocess.run(["rfkill", "unblock", "bluetooth"], capture_output=True)
            GLib.timeout_add(600, self._power_on)
            return
        self._set(self.adapter[0], "org.bluez.Adapter1", "Powered", GLib.Variant("b", want),
                  done=lambda e: (self._error(None, e), self.refresh()) if e else None)

    def _power_on(self):
        self.refresh()
        if self.adapter:
            self._set(self.adapter[0], "org.bluez.Adapter1", "Powered", GLib.Variant("b", True),
                      done=lambda e: (self._error(None, e), self.refresh()) if e else None)
        return GLib.SOURCE_REMOVE

    def _toggle_search(self):
        if not self.adapter:
            return
        if self.adapter[1].get("Discovering"):
            self._stop_search()
            return
        self._call(self.adapter[0], "org.bluez.Adapter1", "StartDiscovery",
                   done=lambda e: self._error(None, e) if e and "InProgress" not in e.message else None)
        # A search left running drains batteries and slows the Wi-Fi next to it.
        self.search_timer = GLib.timeout_add_seconds(SEARCH_SECONDS, self._stop_search, True)

    def _stop_search(self, from_timer=False):
        if self.search_timer and not from_timer:
            GLib.source_remove(self.search_timer)
        self.search_timer = None
        if self.adapter:
            self._call(self.adapter[0], "org.bluez.Adapter1", "StopDiscovery")
        return GLib.SOURCE_REMOVE

    # -- the pairing agent ---------------------------------------------------

    def _register_agent(self):
        info = Gio.DBusNodeInfo.new_for_xml(AGENT_XML).interfaces[0]
        try:
            self.agent_id = self.bus.register_object(AGENT_PATH, info, self._agent_call, None, None)
        except GLib.Error:
            self.agent_id = None
            return
        self._call("/org/bluez", "org.bluez.AgentManager1", "RegisterAgent",
                   GLib.Variant("(os)", (AGENT_PATH, "KeyboardDisplay")))
        if not blueman_running():
            self._call("/org/bluez", "org.bluez.AgentManager1", "RequestDefaultAgent",
                       GLib.Variant("(o)", (AGENT_PATH,)))

    def _name_of(self, path):
        for d in self.devices:
            if d.path == path:
                return d.name or d.address
        return path.rsplit("dev_", 1)[-1].replace("_", ":")

    def _agent_call(self, _bus, _sender, _path, _iface, method, params, invocation):
        args = params.unpack()
        reject = lambda: invocation.return_dbus_error("org.bluez.Error.Rejected", "Rejected")
        if method in ("Release", "Cancel"):
            if self.agent_dialog:
                self.agent_dialog.force_close()
            invocation.return_value(None)
        elif method == "RequestConfirmation":
            device, passkey = args
            self._ask(self.s["code_confirm"].format(name=self._name_of(device), code=f"{passkey:06d}"),
                      lambda: invocation.return_value(None), reject)
        elif method == "RequestAuthorization":
            self._ask(self.s["auth_ask"].format(name=self._name_of(args[0])),
                      lambda: invocation.return_value(None), reject)
        elif method == "AuthorizeService":
            device = args[0]
            if any(d.path == device and (d.trusted or d.paired) for d in self.devices):
                invocation.return_value(None)
            else:
                self._ask(self.s["auth_ask"].format(name=self._name_of(device)),
                          lambda: invocation.return_value(None), reject)
        elif method in ("DisplayPasskey", "DisplayPinCode"):
            code = f"{args[1]:06d}" if method == "DisplayPasskey" else args[1]
            self._ask(self.s["code_show"].format(name=self._name_of(args[0]), code=code),
                      None, None)
            invocation.return_value(None)
        elif method == "RequestPinCode":
            self._ask(self.s["pin_ask"].format(name=self._name_of(args[0])),
                      lambda text: invocation.return_value(GLib.Variant("(s)", (text,))),
                      reject, entry=True)
        elif method == "RequestPasskey":
            self._ask(self.s["pass_ask"].format(name=self._name_of(args[0])),
                      lambda text: invocation.return_value(GLib.Variant("(u)", (int(text or 0),)))
                      if text.isdigit() else reject(),
                      reject, entry=True)
        else:
            reject()

    def _ask(self, body, accept, refuse, entry=False):
        """One dialog for every agent question. With no `accept`, it only shows."""
        dialog = Adw.AlertDialog(heading=self.s["code_q"], body=body)
        field = None
        if entry:
            field = Gtk.Entry()
            field.set_activates_default(True)
            dialog.set_extra_child(field)
        if accept:
            dialog.add_response("reject", self.s["reject"])
            dialog.add_response("ok", self.s["confirm"])
            dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("ok")
            dialog.set_close_response("reject")
        else:
            dialog.add_response("ok", self.s["ok"])
        answered = [False]

        def respond(_d, response):
            if answered[0]:
                return
            answered[0] = True
            self.agent_dialog = None
            if accept is None:
                return
            if response == "ok":
                accept(field.get_text().strip()) if entry else accept()
            else:
                refuse()
        dialog.connect("response", respond)
        self.agent_dialog = dialog
        self.present()
        dialog.present(self)

    def reload_theme(self):
        Gtk.Settings.get_default().reset_property("gtk-theme-name")
        self.shape = None
        self.refresh()
        return GLib.SOURCE_REMOVE


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def do_command_line(self, _cmdline):
        win = self.props.active_window
        if win is None:
            win = Blue(self)
            signal.signal(signal.SIGUSR1, lambda *_: GLib.idle_add(win.reload_theme))
        win.present()
        return 0


if __name__ == "__main__":
    App().run(sys.argv)
