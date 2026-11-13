#!/usr/bin/env python3
"""HyprDuo -- the same sound on several outputs at once (bilingual FR / EN).

Two headphones on one film, a speaker plus the laptop: the ticks are where the
sound goes. One ticked is an ordinary output; tick a second and PipeWire plays
everything on all of them together. There is no switch on top of that.

How it works, so the next reader does not have to dig:

  * Sharing is a `module-combine-sink` loaded into pipewire-pulse. It lives as
    long as pipewire-pulse does, not as long as this window: close the popup
    and the sound keeps going everywhere. Nothing is written into PipeWire's
    configuration, nothing restarts.
  * PipeWire's version of that module turns its `sinks=` list into match
    rules. An output that drops out (a headset going out of range) and comes
    back rejoins the share on its own. Note the argument really is `sinks=`:
    PulseAudio's old `slaves=` is accepted here but ignored, and the module
    then combines *every* output on the machine, speakers included.
  * `latency_compensate=true` delays the faster outputs to line up with the
    slowest. Bluetooth latency is reported, but not always truthfully, so each
    output also gets a manual offset (`set-port-latency-offset`) for the echo
    that is left when two speakers share a room.
  * Streams follow the default output, so making the combined sink the
    default moves whatever is playing without touching each stream.

Sharing is deliberately not restored at login: at that moment the headsets are
not connected yet, and a default output with nothing behind it is silence.
Nothing about the ticks is stored either: they are read back from PipeWire.

Like HyprWhale, it has no palette of its own: it inherits GTK's, which matugen
regenerates on every wallpaper change. SIGUSR1 reloads the theme.
"""

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

APP_ID = "dev.local.HyprDuo"
LANG_FILE = os.path.expanduser("~/.config/hypr/scripts/.hyprsettings-lang")
STATE_FILE = os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
    "hyprduo.json")

# Two names, used in turn: changing the members loads the new combination
# first, moves the default onto it, and only then drops the old one. With a
# single name the old module would have to go first, and the music with it.
SINKS = ("hyprduo-a", "hyprduo-b")

WIDTH = 400
MARGIN = 12
TOP = 30            # fallback; the real one is read from Hyprland, see _monitor
POLL_MS = 4000      # Bluetooth (pairing, battery) has no event stream here

# Past this many Bluetooth outputs the radio saturates, and the chip shares
# its antenna with the Wi-Fi.
BT_COMFORT = 2

# Codecs heavy enough that two of them at once make the radio crackle.
HEAVY = {"ldac", "aptx_hd"}

G_HEAD = "\U000f02cb"      # headphones
G_SPEAKER = "\U000f04c3"
G_LAPTOP = "\U000f0322"
G_SCREEN = "\U000f0379"
G_BT = "\U000f00af"
G_LOGO = "\U000f0d38"      # several speakers
G_LOCK = "\U000f033e"

T = {
    "fr": {
        "title": "Son partagé", "sink": "Son partagé",
        "pinned": "Verrouillée : Super + A ou Échap pour fermer",
        "on": "Partagé", "off": "Une sortie",
        "lead_off": "Coche une deuxième sortie pour y envoyer le même son",
        "lead_on": "Le même son sur {names}",
        "lead_wait": "Partagé, en attente de ses sorties",
        "none": "Aucune sortie", "none_sub": "PipeWire ne voit aucune carte son",
        "default": "Par défaut",
        "p_speaker": "Haut-parleurs", "p_jack": "Prise casque",
        "k_bt": "Bluetooth", "k_builtin": "Intégré", "k_usb": "USB", "k_hdmi": "HDMI",
        "absent": "Absente", "absent_sub": "Reviendra dans le partage dès qu'elle se reconnecte",
        "hfp": "Micro actif : qualité réduite",
        "a2dp": "Repasser en A2DP",
        "codec": "Codec", "auto": "Auto",
        "codec_sub": "SBC tient le mieux à plusieurs",
        "offset": "Décalage", "offset_sub": "Retarde cette sortie pour la caler sur les autres",
        "alone": "Utiliser seule", "disconnect": "Déconnecter",
        "devices": "Bluetooth",
        "connect": "Connecter", "connecting": "Connexion…",
        "audio_on": "Activer l'audio",
        "d_off": "Déconnecté", "d_noaudio": "Connecté, audio coupé",
        "bt_off": "Bluetooth éteint", "bt_off_sub": "Allume-le pour retrouver tes casques",
        "power_on": "Allumer",
        "w_dead": "Aucune sortie du partage n'est branchée : le son ne sort nulle part.",
        "stop": "Arrêter",
        "w_crowd": "Au-delà de {n} appareils Bluetooth la radio sature : attends-toi à des coupures. "
                   "Un second dongle, ou le codec SBC, aident.",
        "w_heavy": "LDAC et aptX HD chargent la radio : passe en SBC ou AAC (⋯) si ça grésille.",
        "w_echo": "Écho dans une même pièce ? Retarde la sortie la plus rapide (⋯ › Décalage).",
        "mixer": "Mixeur complet", "bt_settings": "Réglages Bluetooth",
    },
    "en": {
        "title": "Shared audio", "sink": "Shared audio",
        "pinned": "Locked: Super + A or Esc to close",
        "on": "Shared", "off": "One output",
        "lead_off": "Tick a second output to send it the same sound",
        "lead_on": "The same sound on {names}",
        "lead_wait": "Shared, waiting for its outputs",
        "none": "No output", "none_sub": "PipeWire sees no sound card",
        "default": "Default",
        "p_speaker": "Speakers", "p_jack": "Headphone jack",
        "k_bt": "Bluetooth", "k_builtin": "Built-in", "k_usb": "USB", "k_hdmi": "HDMI",
        "absent": "Away", "absent_sub": "Rejoins the share as soon as it reconnects",
        "hfp": "Mic in use: lower quality",
        "a2dp": "Back to A2DP",
        "codec": "Codec", "auto": "Auto",
        "codec_sub": "SBC copes best with several",
        "offset": "Offset", "offset_sub": "Delays this output to line it up with the others",
        "alone": "Use on its own", "disconnect": "Disconnect",
        "devices": "Bluetooth",
        "connect": "Connect", "connecting": "Connecting…",
        "audio_on": "Turn audio on",
        "d_off": "Disconnected", "d_noaudio": "Connected, audio off",
        "bt_off": "Bluetooth is off", "bt_off_sub": "Turn it on to find your headsets",
        "power_on": "Turn on",
        "w_dead": "None of the shared outputs is connected: the sound goes nowhere.",
        "stop": "Stop",
        "w_crowd": "Past {n} Bluetooth devices the radio saturates: expect dropouts. "
                   "A second dongle, or the SBC codec, help.",
        "w_heavy": "LDAC and aptX HD load the radio: switch to SBC or AAC (⋯) if it crackles.",
        "w_echo": "Echo in one room? Delay the fastest output (⋯ › Offset).",
        "mixer": "Full mixer", "bt_settings": "Bluetooth settings",
    },
}

CODECS = {
    "sbc": "SBC", "sbc_xq": "SBC-XQ", "aac": "AAC", "aptx": "aptX",
    "aptx_hd": "aptX HD", "aptx_ll": "aptX LL", "ldac": "LDAC", "lc3": "LC3",
    "lc3plus_h3": "LC3plus", "opus_05": "Opus", "faststream": "FastStream",
    "cvsd": "CVSD", "msbc": "mSBC",
}

CSS = b"""
/* Translucent, like the notch and HyprWhale: the window draws nothing, the
   surface lays the background down and Hyprland's blur does the rest. */
window, window.background { background: transparent; }
.hd-root .hd-surface {
  background: alpha(@window_bg_color, 0.85);
  border-radius: 10px;
}
.hd-root, .hd-root button, .hd-root label {
  font-family: "JetBrainsMono Nerd Font Propo", "JetBrains Mono", monospace;
  font-size: 12px;
}
.hd-root .hd-logo { font-size: 16px; color: @accent_color; }
.hd-root .hd-title { font-weight: 700; font-size: 13px; }
.hd-head { padding: 10px 12px; }
.hd-sep { background: alpha(currentColor, 0.14); min-height: 1px; }

.hd-root .hd-chip {
  font-size: 11px; padding: 2px 10px; border-radius: 999px;
  background: alpha(currentColor, 0.12);
}
.hd-root .hd-chip.hd-live { background: alpha(@accent_color, 0.20); color: @accent_color; }
.hd-root .hd-sec { font-size: 10px; letter-spacing: 1.6px; opacity: 0.65; }
.hd-root .hd-count {
  font-size: 11px; padding: 1px 9px; border-radius: 999px;
  background: alpha(@accent_color, 0.20); color: @accent_color;
}
.hd-root .hd-name { font-weight: 700; font-size: 12.5px; }
.hd-root .hd-meta { font-size: 11px; opacity: 0.66; }


.hd-row {
  padding: 7px 9px; border-radius: 8px;
  border: 1px solid transparent;
}
.hd-row.hd-picked {
  background: alpha(@accent_color, 0.08);
  border-color: alpha(@accent_color, 0.22);
}
.hd-row.hd-gone { opacity: 0.55; }
.hd-root .hd-icon { font-size: 17px; min-width: 22px; }
.hd-root .hd-picked .hd-icon { color: @accent_color; }

/* State colours stay outside the theme: a warning has to read as one even
   when the wallpaper hands out an amber accent. */
.hd-root .hd-warn { color: #e8b339; }
.hd-hint {
  margin: 4px 8px 2px 8px; padding: 7px 10px; border-radius: 8px;
  background: alpha(#e8b339, 0.12);
}
.hd-root .hd-hint label { font-size: 11px; }
/* bare classes lose to `.hd-root label`, hence the prefix on every label rule */
.hd-root .hd-soft { margin: 2px 14px 4px 14px; }

.hd-root button.hd-item {
  min-height: 28px; padding: 0 10px;
  background: none; border: none; box-shadow: none;
}
.hd-root button.hd-item:hover { background: alpha(@accent_color, 0.14); }
.hd-root button.hd-item.hd-current { color: @accent_color; }

.hd-root button.hd-act, .hd-root menubutton.hd-act > button {
  min-height: 23px; padding: 0 10px; font-size: 11px;
  border-radius: 7px; background: none;
  border: 1px solid alpha(currentColor, 0.28); box-shadow: none;
}
/* the menu button is a box around a button: the frame belongs on the inner one */
.hd-root menubutton.hd-act > button { min-width: 0; padding: 0 8px; }
.hd-root button.hd-act:hover,
.hd-root menubutton.hd-act > button:hover,
.hd-root menubutton.hd-act > button:checked { background: alpha(@accent_color, 0.16); }
.hd-root button.hd-act:disabled { opacity: 0.35; }
.hd-root button.hd-go { border-color: alpha(@accent_color, 0.55); color: @accent_color; }

.hd-root scale { padding: 0; margin: 0 2px; }
.hd-root scale trough { min-height: 4px; }
.hd-root scale slider { min-width: 12px; min-height: 12px; margin: -5px; }
.hd-pop label.hd-sec { margin: 6px 10px 2px 10px; }
.hd-pop .hd-meta { margin: 0 10px 4px 10px; }
"""


# -- small helpers ----------------------------------------------------------

def hypr_socket():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not sig:
        return None
    path = f"/run/user/{os.getuid()}/hypr/{sig}/.socket.sock"
    return path if os.path.exists(path) else None


SOCKET = hypr_socket()
SELF = f'window="class:{APP_ID}"'


def ipc(command):
    """Straight to Hyprland's socket: fast enough to run on every relayout."""
    if not SOCKET:
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sk:
            sk.settimeout(0.3)
            sk.connect(SOCKET)
            sk.sendall(command.encode())
            sk.recv(64)
    except OSError:
        pass


def frame(x, y, width, height):
    """Size and corner in one Lua chunk. Hyprland runs a Lua config here: the
    legacy `dispatch movewindowpixel exact …` string is rejected by it."""
    ipc("/eval "
        f"hl.dispatch(hl.dsp.window.resize{{exact=true, x={width}, y={height}, {SELF}}}) "
        f"hl.dispatch(hl.dsp.window.move{{exact=true, x={x}, y={y}, {SELF}}})")


def pin_on_top():
    """Hyprland's pin: on every workspace, and above the other floating
    windows. A locked popup that any window could bury would be no lock."""
    ipc(f'/eval hl.dispatch(hl.dsp.window.pin({{ action = "enable", {SELF} }}))')


def lang():
    try:
        with open(LANG_FILE, encoding="utf-8") as fh:
            v = fh.read().strip()
            if v in T:
                return v
    except OSError:
        pass
    return "fr"


def run(*argv, timeout=6):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return None


def pactl(*args, timeout=6):
    return run("pactl", *args, timeout=timeout)


def pactl_json(*args):
    out = pactl("-f", "json", *args)
    try:
        return json.loads(out.stdout) if out and out.returncode == 0 else []
    except ValueError:
        return []


def spawn(*argv):
    try:
        subprocess.Popen(argv, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp, STATE_FILE)
    except (OSError, RuntimeError):
        # RuntimeError: an action thread and the main loop both touch the
        # state; a dump caught mid-change is dropped, the next one catches up.
        pass


def codec_label(profile):
    """a2dp-sink-aac -> AAC; the bare a2dp-sink lets PipeWire choose."""
    rest = profile[len("a2dp-sink"):].lstrip("-")
    return CODECS.get(rest, rest.upper()) if rest else None


def percent(volume):
    try:
        return max(int(ch["value_percent"].rstrip("%")) for ch in volume.values())
    except (AttributeError, ValueError, KeyError):
        return 0


# -- the model --------------------------------------------------------------

class Output:
    """A sink worth sharing to: a real card, wired or Bluetooth."""

    def __init__(self, name):
        self.name = name
        self.label = name
        self.kind = "builtin"
        self.glyph = G_SPEAKER
        self.present = True
        self.volume = 100
        self.card = None
        self.port = None
        self.offset = 0          # ms
        self.mac = None
        self.codec = None
        self.codecs = []         # [(profile, label)]
        self.profile = None
        self.hfp = False
        self.battery = None

    def key(self):
        """Everything that changes the layout. Volume and offset are left out:
        those are updated in place, so a slider is never rebuilt under the
        finger dragging it."""
        return (self.name, self.label, self.kind, self.present, self.codec,
                tuple(self.codecs), self.profile, self.hfp, self.battery)


class Device:
    """A paired Bluetooth audio device that has no output right now."""

    def __init__(self, mac, name, connected, glyph, battery):
        self.mac, self.name, self.connected = mac, name, connected
        self.glyph, self.battery = glyph, battery

    def key(self):
        return (self.mac, self.name, self.connected, self.battery)


class Snapshot:
    def __init__(self):
        self.outputs = []
        self.devices = []
        self.default = None
        self.share = None        # the combined sink's name, when sharing
        self.module = None       # its module index
        self.members = []        # what that module was asked to combine
        self.bt = "absent"       # absent / off / on

    def key(self):
        return (tuple(o.key() for o in self.outputs),
                tuple(d.key() for d in self.devices),
                self.default, self.share, tuple(self.members), self.bt)


def current_share():
    """(sink name, module index) of the share as pipewire-pulse has it now.
    Actions read this rather than the last snapshot, which may be stale."""
    for s in pactl_json("list", "sinks"):
        if s.get("name") in SINKS:
            return s["name"], s.get("owner_module")
    return None, None


def configured_sink():
    """The output the user *chose*, as WirePlumber keeps it -- not the one in
    use. They differ: with nothing chosen, WirePlumber picks by priority and
    a headset outranks the speakers. Pinning the one in use instead is what
    made the speakers stick after the share, headset or not."""
    out = run("pw-metadata", "0", "default.configured.audio.sink", timeout=3)
    m = re.search(r'"name"\s*:\s*"([^"]+)"', out.stdout if out else "")
    return m.group(1) if m and m.group(1) not in SINKS else None


def bluetooth():
    """(power, {mac: (name, connected, glyph, battery)}) for audio devices."""
    if shutil.which("bluetoothctl") is None:
        return "absent", {}
    show = run("bluetoothctl", "show", timeout=3)
    if not show or show.returncode != 0 or "Powered:" not in show.stdout:
        return "absent", {}
    power = "on" if re.search(r"Powered:\s*yes", show.stdout) else "off"

    found = {}
    paired = run("bluetoothctl", "devices", "Paired", timeout=3)
    for line in (paired.stdout if paired else "").splitlines():
        m = re.match(r"Device\s+([0-9A-F:]{17})\s+(.*)", line.strip())
        if not m:
            continue
        mac = m.group(1)
        info = run("bluetoothctl", "info", mac, timeout=3)
        text = info.stdout if info else ""
        icon = (re.search(r"Icon:\s*(\S+)", text) or [None, ""])[1]
        # Audio Sink (A2DP) or a hands-free unit: anything that can play.
        audio = ("0000110b" in text or "0000111e" in text
                 or icon.startswith("audio"))
        if not audio:
            continue
        name = (re.search(r"Alias:\s*(.+)", text) or [None, m.group(2)])[1].strip()
        connected = bool(re.search(r"\n\s*Connected:\s*yes", text))
        bat = re.search(r"Battery Percentage:\s*\S+\s*\((\d+)\)", text)
        glyph = G_SPEAKER if "speaker" in icon else G_HEAD
        found[mac] = (name, connected, glyph, int(bat.group(1)) if bat else None)
    return power, found


def snapshot(selected, names=None):
    snap = Snapshot()
    sinks = pactl_json("list", "sinks")
    cards = {c.get("name"): c for c in pactl_json("list", "cards")}
    out = pactl("get-default-sink")
    snap.default = out.stdout.strip() if out and out.returncode == 0 else None
    snap.bt, paired = bluetooth()

    by_name = {}
    for s in sinks:
        name = s.get("name", "")
        props = s.get("properties", {})
        if name in SINKS:
            snap.share = name
            snap.module = s.get("owner_module")
            continue
        api = props.get("device.api")
        if api not in ("alsa", "bluez5"):
            continue                       # virtual sinks, effects, our own

        o = Output(name)
        o.label = s.get("description") or name
        o.volume = percent(s.get("volume", {}))
        o.port = s.get("active_port")
        o.card = props.get("device.name")
        card = cards.get(o.card) or {}
        port = (card.get("ports") or {}).get(o.port) or {}
        try:
            o.offset = int(str(port.get("latency_offset", "0")).split()[0]) // 1000
        except ValueError:
            o.offset = 0

        ff = (props.get("device.form_factor") or "") + (props.get("device.icon_name") or "")
        if api == "bluez5":
            o.kind = "bt"
            o.mac = props.get("api.bluez5.address")
            o.codec = props.get("api.bluez5.codec")
            o.profile = card.get("active_profile") or props.get("api.bluez5.profile")
            o.hfp = bool(o.profile and o.profile.startswith("headset-head-unit"))
            o.codecs = sorted(
                ((p, codec_label(p)) for p, v in (card.get("profiles") or {}).items()
                 if p.startswith("a2dp-sink") and v.get("available", True)),
                key=lambda pc: (pc[1] is not None, pc[1] or ""))
            o.glyph = G_SPEAKER if "speaker" in ff else G_HEAD
            if o.mac in paired:
                o.battery = paired[o.mac][3]
        else:
            ptype = (port.get("type") or "").lower()
            if props.get("device.bus") == "usb":
                o.kind = "usb"
            elif ptype in ("hdmi", "spdif") or "hdmi" in name:
                o.kind = "hdmi"
                o.glyph = G_SCREEN
            if o.kind != "hdmi":
                o.glyph = G_HEAD if ("head" in ff or ptype == "headphones") else (
                    G_LAPTOP if o.kind == "builtin" else G_SPEAKER)
        by_name[name] = o

    if snap.module is not None:
        for line in (pactl("list", "short", "modules").stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[0] == str(snap.module):
                m = re.search(r"\bsinks=(\S+)", parts[2])
                snap.members = m.group(1).split(",") if m else []

    # Outputs ticked but not here (a headset out of range) stay on the list,
    # greyed: the share will take them back when they reconnect.
    wanted = list(dict.fromkeys((snap.members if snap.share else []) + list(selected)))
    for name in wanted:
        if name not in by_name and name.startswith("bluez_output."):
            o = Output(name)
            o.present = False
            o.kind = "bt"
            o.glyph = G_HEAD
            mac = name.split(".")[1].replace("_", ":") if "." in name else None
            o.mac = mac
            o.label = (paired[mac][0] if mac in paired
                       else (names or {}).get(name, name))
            by_name[name] = o

    order = {"bt": 0, "usb": 1, "builtin": 2, "hdmi": 3}
    snap.outputs = sorted(by_name.values(), key=lambda o: (order[o.kind], o.label.lower()))

    live = {o.mac for o in snap.outputs if o.present and o.mac}
    for mac, (name, connected, glyph, bat) in paired.items():
        if mac not in live:
            snap.devices.append(Device(mac, name, connected, glyph, bat))
    snap.devices.sort(key=lambda d: (not d.connected, d.name.lower()))
    return snap


# -- the window -------------------------------------------------------------

class Duo(Adw.ApplicationWindow):
    def __init__(self, app, pinned=False):
        super().__init__(application=app, default_width=WIDTH)
        # Opened from the keyboard, the pointer is somewhere else on the
        # screen. With focus following the mouse, the trip to the popup crosses
        # other windows, and a popup that closes on focus loss is gone before
        # the pointer arrives. So that one stays until asked to go, like the
        # notch on Super+Shift+N.
        self.pinned = pinned
        self.s = T[lang()]
        self.set_title(self.s["title"])
        self.add_css_class("hd-root")

        self.state = load_state()
        self.selected = []
        self.snap = None
        self.shape = None
        self.busy = False
        self.connecting = set()
        self.sliders = {}
        self.touched = {}
        self.menus_open = 0
        self.dirty = False
        self.screen = None
        self.top = TOP
        self.height = None
        self._probing = False
        self._again = False
        self._poke_id = None
        self._quiet = False
        # Bumped by every action. A read started before an action finished
        # describes the world before it, and is thrown away.
        self.gen = 0
        self.lock = threading.Lock()

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.root.add_css_class("hd-surface")
        self.toasts = Adw.ToastOverlay(child=self.root)
        self.set_content(self.toasts)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        self._had_focus = False
        self._closing = None
        self.connect("notify::is-active", self._on_focus)
        self.connect("close-request", self._on_close)
        self.connect("map", lambda _w: GLib.timeout_add(150, self._refit))

        self._render()
        self.refresh()
        self._watch()
        GLib.timeout_add(POLL_MS, self._tick)

    # -- focus, like a tray menu -------------------------------------------

    def set_pinned(self, pinned):
        self.pinned = pinned
        if pinned and self._closing:
            GLib.source_remove(self._closing)
            self._closing = None
        if pinned:
            pin_on_top()
        self._show(force=True)

    def _on_focus(self, *_):
        if self.pinned:
            return
        if self.is_active():
            self._had_focus = True
            if self._closing:
                GLib.source_remove(self._closing)
                self._closing = None
            return
        if not self._had_focus or self.menus_open:
            return
        # A grace delay: with follow_mouse, the pointer merely passing by must
        # not be enough to close it.
        if self._closing is None:
            self._closing = GLib.timeout_add(450, self._close_now)

    def _close_now(self):
        self._closing = None
        if not self.is_active() and not self.menus_open:
            self.close()
        return GLib.SOURCE_REMOVE

    def leaving(self):
        """True while the popup has just lost focus: the click that took it
        away was most likely on the bar, asking for it to go."""
        return self._closing is not None

    def _on_key(self, _c, keyval, _kc, _st):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return Gdk.EVENT_STOP
        return Gdk.EVENT_PROPAGATE

    def _on_close(self, *_):
        proc = getattr(self, "_events", None)
        if proc and proc.poll() is None:
            proc.terminate()
        return False

    # -- reading the state -------------------------------------------------

    def _watch(self):
        """`pactl subscribe` tells us when a card or a sink comes or goes, so
        a headset that connects shows up without waiting for the poll."""
        try:
            self._events = subprocess.Popen(
                ["pactl", "subscribe"], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True)
        except OSError:
            return

        def read():
            for line in self._events.stdout:
                if "sink-input" in line or "source" in line or "client" in line:
                    continue
                if " sink " in line or " card " in line or " server" in line:
                    GLib.idle_add(self._poke)
        threading.Thread(target=read, daemon=True).start()

    def _poke(self):
        if self._poke_id is None:
            self._poke_id = GLib.timeout_add(180, self._poked)
        return GLib.SOURCE_REMOVE

    def _poked(self):
        self._poke_id = None
        self.refresh()
        return GLib.SOURCE_REMOVE

    def _tick(self):
        self.refresh()
        return GLib.SOURCE_CONTINUE

    def refresh(self):
        if self._probing:
            self._again = True
            return GLib.SOURCE_REMOVE
        self._probing = True
        selected = list(self.selected)
        names = dict(self.state.get("names") or {})
        gen = self.gen

        def work():
            snap = snapshot(selected, names)
            GLib.idle_add(self._apply, snap, gen)
        threading.Thread(target=work, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _apply(self, snap, gen):
        self._probing = False
        if gen != self.gen:
            self.refresh()
            return GLib.SOURCE_REMOVE
        self.snap = snap
        if not self.busy:
            # The ticks *are* where the sound goes, so they are read, never
            # stored: the share's members, or else the one default output.
            # Not while an action of ours is in flight, or a poll landing in
            # between would put back the ticks the user just changed.
            names = {o.name for o in snap.outputs}
            self.selected = (list(snap.members) if snap.share
                             else [snap.default] if snap.default in names else [])
        self._learn(snap)
        self._show()
        if self._again:
            self._again = False
            self.refresh()
        return GLib.SOURCE_REMOVE

    def _learn(self, snap):
        """Keep the name of every ticked output seen: once it is out of range
        nothing else knows it any more, and the row would read
        `bluez_output.AA_BB_…`."""
        names = self.state.setdefault("names", {})
        changed = False
        for o in snap.outputs:
            if o.present and o.name in self.selected and names.get(o.name) != o.label:
                names[o.name] = o.label
                changed = True
        if changed:
            save_state(self.state)

    def _show(self, force=False):
        snap = self.snap
        if snap is None:
            return
        if force:
            self.shape = None
        shape = snap.key() + (tuple(self.selected), self.busy, tuple(sorted(self.connecting)))
        if shape != self.shape:
            self.shape = shape
            if self.menus_open:
                self.dirty = True          # never pull a menu from under the pointer
            else:
                self._render()
        else:
            self._update_in_place()

    def _update_in_place(self):
        self._quiet = True
        now = time.monotonic()
        for o in self.snap.outputs:
            scale = self.sliders.get(o.name)
            if scale and now - self.touched.get(o.name, 0) > 1.5:
                scale.set_value(o.volume)
        self._quiet = False

    # -- rendering ---------------------------------------------------------

    @staticmethod
    def _sep():
        s = Gtk.Box()
        s.add_css_class("hd-sep")
        return s

    @staticmethod
    def _label(text, *classes, wrap=False, ellipsize=False):
        lbl = Gtk.Label(label=text, xalign=0)
        for c in classes:
            lbl.add_css_class(c)
        if wrap:
            lbl.set_wrap(True)
            lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if ellipsize:
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
        return lbl

    def _render(self):
        self.dirty = False
        self.sliders = {}
        while (child := self.root.get_first_child()) is not None:
            self.root.remove(child)

        self.root.append(self._header())
        self.root.append(self._sep())
        if self.snap is None:
            return

        self.root.append(self._lead())
        self.root.append(self._outputs())
        for hint in self._hints():
            self.root.append(hint)

        devices = self._devices()
        if devices is not None:
            self.root.append(self._sep())
            self.root.append(self._section(self.s["devices"], None))
            self.root.append(devices)

        self.root.append(self._sep())
        self.root.append(self._footer())
        GLib.timeout_add(30, self._fit)

    def _header(self):
        box = Gtk.Box(spacing=9)
        box.add_css_class("hd-head")
        box.append(self._label(G_LOGO, "hd-logo"))
        box.append(self._label(self.s["title"], "hd-title"))
        box.append(Gtk.Box(hexpand=True))

        if self.pinned:
            lock = self._label(G_LOCK, "hd-meta")
            lock.set_tooltip_text(self.s["pinned"])
            box.append(lock)

        sharing = bool(self.snap and self.snap.share)
        chip = Gtk.Label(label=f"{self.s['on']} · {len(self.snap.members)}"
                         if sharing else self.s["off"])
        chip.add_css_class("hd-chip")
        if sharing:
            chip.add_css_class("hd-live")
        box.append(chip)
        return box

    def _lead(self):
        """What the ticks do, in one line: there is no switch. One ticked
        output is just where the sound goes; tick a second and it is shared."""
        sharing = bool(self.snap.share)
        if sharing:
            names = [self._name(o) for o in self.snap.outputs
                     if o.name in self.snap.members and o.present]
            text = (self.s["lead_on"].format(names=", ".join(names)) if names
                    else self.s["lead_wait"])
        else:
            text = self.s["lead_off"]
        lbl = self._label(text, "hd-meta", wrap=True)
        lbl.set_margin_start(14); lbl.set_margin_end(14)
        lbl.set_margin_top(9); lbl.set_margin_bottom(6)
        return lbl

    def _section(self, title, count):
        box = Gtk.Box(spacing=8)
        box.set_margin_start(13); box.set_margin_end(11)
        box.set_margin_top(9); box.set_margin_bottom(4)
        box.append(self._label(title.upper(), "hd-sec"))
        box.append(Gtk.Box(hexpand=True))
        if count:
            box.append(self._label(count, "hd-count"))
        return box

    def _outputs(self):
        if not self.snap.outputs:
            return self._notice(self.s["none"], self.s["none_sub"])
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.set_margin_start(6); inner.set_margin_end(6); inner.set_margin_bottom(4)
        for o in self.snap.outputs:
            inner.append(self._row(o))
        sc = Gtk.ScrolledWindow(child=inner)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_propagate_natural_height(True)
        sc.set_max_content_height(420)
        return sc

    # The card's own name ("Ryzen HD Audio Controller Analog Stereo") says
    # nothing about where the sound comes out; the port does.
    PORTS = {"analog-output-speaker": "p_speaker", "analog-output-headphones": "p_jack"}

    def _name(self, o):
        key = self.PORTS.get(o.port) if o.kind == "builtin" else None
        return self.s[key] if key else o.label

    def _meta(self, o):
        if not o.present:
            return self.s["absent"]
        bits = [self.s["k_" + o.kind]]
        if o.codec:
            bits.append(CODECS.get(o.codec, o.codec.upper()))
        if o.battery is not None:
            bits.append(f"{o.battery} %")
        if o.offset:
            bits.append(f"+{o.offset} ms")
        return "  ·  ".join(bits)

    def _row(self, o):
        sharing = bool(self.snap.share)
        picked = o.name in self.selected
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("hd-row")
        if picked:
            card.add_css_class("hd-picked")
        if not o.present:
            card.add_css_class("hd-gone")

        top = Gtk.Box(spacing=10)
        check = Gtk.CheckButton(active=picked, valign=Gtk.Align.CENTER)
        last = picked and len(self.selected) == 1
        check.set_sensitive(not self.busy and not last)
        check.connect("toggled", lambda b, n=o.name: self._on_pick(n, b.get_active()))
        top.append(check)
        top.append(self._label(o.glyph, "hd-icon"))

        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        texts.append(self._label(self._name(o), "hd-name", ellipsize=True))
        texts.append(self._label(self._meta(o), "hd-meta", ellipsize=True))
        top.append(texts)

        if not sharing and o.name == self.snap.default:
            chip = self._label(self.s["default"], "hd-chip")
            chip.set_valign(Gtk.Align.CENTER)
            top.append(chip)
        if o.present:
            top.append(self._menu(o))
        card.append(top)

        if not o.present and picked:
            card.append(self._label(self.s["absent_sub"], "hd-meta", wrap=True))

        if o.hfp:
            warn = Gtk.Box(spacing=8)
            warn.append(self._label(self.s["hfp"], "hd-meta", "hd-warn", ellipsize=True))
            warn.append(Gtk.Box(hexpand=True))
            fix = Gtk.Button(label=self.s["a2dp"])
            fix.add_css_class("hd-act")
            fix.connect("clicked", lambda _b: self._act(self._a2dp, o.card))
            warn.append(fix)
            card.append(warn)

        # Each listener sets their own level: that is the whole point of two
        # headsets on one film. Only while sharing, or it is just the volume.
        if sharing and picked and o.present:
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            scale.set_draw_value(False)
            scale.set_hexpand(True)
            scale.set_value(o.volume)
            scale.set_margin_start(32)
            scale.connect("value-changed", lambda w, n=o.name: self._on_volume(n, w))
            self.sliders[o.name] = scale
            card.append(scale)
        return card

    def _menu(self, o):
        pop = Gtk.Popover()
        pop.add_css_class("hd-pop")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.set_margin_top(4); box.set_margin_bottom(5)
        box.set_margin_start(4); box.set_margin_end(4)
        box.set_size_request(230, -1)

        def item(label, cb, current=None):
            # `current` only for a list to choose from: a tick, or room for one
            if current is not None:
                label = ("✓  " if current else "    ") + label
            b = Gtk.Button(label=label)
            b.add_css_class("hd-item")
            if current:
                b.add_css_class("hd-current")
            b.get_child().set_xalign(0.0)
            b.connect("clicked", lambda _x: (pop.popdown(), cb()))
            box.append(b)

        if o.codecs and not o.hfp:
            box.append(self._label(self.s["codec"].upper(), "hd-sec"))
            for profile, label in o.codecs:
                current = (o.profile == profile)
                item(label or self.s["auto"],
                     lambda p=profile: self._act(self._profile, o, p), current)
            box.append(self._label(self.s["codec_sub"], "hd-meta", wrap=True))

        box.append(self._label(self.s["offset"].upper(), "hd-sec"))
        spin_row = Gtk.Box(spacing=8)
        spin_row.set_margin_start(10); spin_row.set_margin_end(10)
        spin = Gtk.SpinButton.new_with_range(0, 1000, 10)
        spin.set_value(o.offset)
        spin.set_sensitive(bool(o.card and o.port))
        spin.connect("value-changed", lambda w: self._on_offset(o, w))
        spin_row.append(spin)
        spin_row.append(self._label("ms", "hd-meta"))
        box.append(spin_row)
        box.append(self._label(self.s["offset_sub"], "hd-meta", wrap=True))

        box.append(self._sep())
        item(self.s["alone"], lambda: self._act(self._alone, o))
        if o.kind == "bt" and o.mac:
            item(self.s["disconnect"], lambda: self._act(self._bt, "disconnect", o.mac))

        pop.set_child(box)
        pop.connect("show", lambda _p: self._menu_state(+1))
        pop.connect("closed", lambda _p: self._menu_state(-1))

        btn = Gtk.MenuButton(valign=Gtk.Align.CENTER)
        btn.set_child(Gtk.Label(label="⋯"))
        btn.add_css_class("hd-act")
        btn.set_always_show_arrow(False)
        btn.set_popover(pop)
        return btn

    def _menu_state(self, delta):
        self.menus_open = max(0, self.menus_open + delta)
        if self.menus_open:
            return
        if self.dirty:
            GLib.idle_add(lambda: (self._render(), GLib.SOURCE_REMOVE)[1])
        # Focus went elsewhere while the menu was up: the focus handler stood
        # aside then, so the closing is ours to start.
        if (not self.pinned and self._had_focus and not self.is_active()
                and self._closing is None):
            self._closing = GLib.timeout_add(450, self._close_now)

    def _hints(self):
        snap = self.snap
        hints = []
        picked = [o for o in snap.outputs if o.name in self.selected]
        bt = [o for o in picked if o.kind == "bt"]
        if snap.share and not any(o.present for o in snap.outputs if o.name in snap.members):
            hints.append(self._hint(self.s["w_dead"], self.s["stop"],
                                    lambda: self._act(self._stop)))
        if len(bt) > BT_COMFORT:
            hints.append(self._hint(self.s["w_crowd"].format(n=BT_COMFORT)))
        if len([o for o in bt if o.present]) >= 2 and any(o.codec in HEAVY for o in bt):
            hints.append(self._hint(self.s["w_heavy"]))
        if snap.share and sum(1 for o in picked if o.present) >= 2:
            soft = self._label(self.s["w_echo"], "hd-meta", "hd-soft", wrap=True)
            hints.append(soft)
        return hints

    def _hint(self, text, action=None, cb=None):
        box = Gtk.Box(spacing=8)
        box.add_css_class("hd-hint")
        lbl = self._label(text, "hd-warn", wrap=True)
        lbl.set_hexpand(True)
        box.append(lbl)
        if action:
            b = Gtk.Button(label=action, valign=Gtk.Align.CENTER)
            b.add_css_class("hd-act")
            b.connect("clicked", lambda _b: cb())
            box.append(b)
        return box

    def _devices(self):
        snap = self.snap
        if snap.bt == "absent":
            return None
        if snap.bt == "off":
            box = Gtk.Box(spacing=8)
            box.set_margin_start(14); box.set_margin_end(10); box.set_margin_bottom(8)
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
            texts.append(self._label(self.s["bt_off"], "hd-name"))
            texts.append(self._label(self.s["bt_off_sub"], "hd-meta", wrap=True))
            box.append(texts)
            on = Gtk.Button(label=self.s["power_on"], valign=Gtk.Align.CENTER)
            on.add_css_class("hd-act"); on.add_css_class("hd-go")
            on.connect("clicked", lambda _b: self._act(self._power))
            box.append(on)
            return box
        if not snap.devices:
            return None

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        inner.set_margin_start(6); inner.set_margin_end(6); inner.set_margin_bottom(4)
        for d in snap.devices:
            row = Gtk.Box(spacing=10)
            row.add_css_class("hd-row")
            row.append(self._label(d.glyph, "hd-icon"))
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
            texts.append(self._label(d.name, "hd-name", ellipsize=True))
            meta = self.s["d_noaudio"] if d.connected else self.s["d_off"]
            if d.battery is not None:
                meta += f"  ·  {d.battery} %"
            texts.append(self._label(meta, "hd-meta", ellipsize=True))
            row.append(texts)

            busy = d.mac in self.connecting
            if d.connected:
                b = Gtk.Button(label=self.s["audio_on"], valign=Gtk.Align.CENTER)
                b.connect("clicked", lambda _b, m=d.mac: self._act(self._audio_on, m))
            else:
                b = Gtk.Button(label=self.s["connecting"] if busy else self.s["connect"],
                               valign=Gtk.Align.CENTER)
                b.connect("clicked", lambda _b, m=d.mac: self._connect(m))
            b.add_css_class("hd-act")
            b.add_css_class("hd-go")
            b.set_sensitive(not busy)
            row.append(b)
            inner.append(row)
        return inner

    def _notice(self, title, subtitle):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(14); box.set_margin_end(14)
        box.set_margin_top(6); box.set_margin_bottom(10)
        box.append(self._label(title, "hd-name"))
        box.append(self._label(subtitle, "hd-meta", wrap=True))
        return box

    def _footer(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.set_margin_start(5); box.set_margin_end(5)
        box.set_margin_top(4); box.set_margin_bottom(5)
        entries = [(self.s["mixer"], ("pavucontrol", "-t", "3"))]
        if self.snap.bt != "absent" and shutil.which("blueman-manager"):
            entries.append((self.s["bt_settings"], ("blueman-manager",)))
        for label, argv in entries:
            if shutil.which(argv[0]) is None:
                continue
            b = Gtk.Button(label=label)
            b.add_css_class("hd-item")
            b.get_child().set_xalign(0.0)
            b.connect("clicked", lambda _b, a=argv: (spawn(*a), self.close()))
            box.append(b)
        return box

    # -- placement ---------------------------------------------------------

    def _monitor(self):
        try:
            mon = subprocess.run(["hyprctl", "monitors", "-j"],
                                 capture_output=True, text=True, timeout=3)
            reserved = 0
            for m in json.loads(mon.stdout or "[]"):
                if m.get("focused") or self.screen is None:
                    scale = m.get("scale") or 1
                    self.screen = (m["x"], m["y"],
                                   round(m["width"] / scale), round(m["height"] / scale))
                    reserved = (m.get("reserved") or [0, 0])[1]
            # Level with the top of the tiled windows: the bar's reserved
            # strip, the outer gap, the border.
            gap = json.loads(run("hyprctl", "getoption", "general:gaps_out", "-j").stdout)
            border = json.loads(run("hyprctl", "getoption", "general:border_size", "-j").stdout)
            top_gap = int(str(gap.get("css", "0")).split()[0])
            self.top = reserved + top_gap + int(border.get("int", 0))
        except (subprocess.SubprocessError, OSError, ValueError, KeyError, AttributeError):
            pass

    def _fit(self):
        """Hyprland keeps a floating window's size and grows it around its
        centre. So on every relayout we ask GTK for the height it wants and
        pin the top-right corner under the bar ourselves."""
        if self.screen is None:
            self._monitor()
        _, natural, _, _ = self.measure(Gtk.Orientation.VERTICAL, WIDTH)
        if self.screen:
            mx, my, mw, mh = self.screen
            natural = min(natural, mh - self.top - MARGIN)
            x, y = mx + mw - WIDTH - MARGIN, my + self.top
        else:
            x, y = None, None
        if natural != self.height and x is not None:
            self.height = natural
            frame(x, y, WIDTH, natural)
        return GLib.SOURCE_REMOVE

    def _refit(self):
        self.height = None
        if self.pinned:
            pin_on_top()
        return self._fit()

    # -- actions -----------------------------------------------------------

    def _act(self, fn, *args):
        """Every action talks to pactl or bluetoothctl, both of which can
        hang for a second: off the main loop, then a fresh read."""
        self.busy = True
        # Not from inside the handler of the checkbox or switch that was just
        # clicked: rebuilding a widget while it is emitting is asking for it.
        GLib.idle_add(lambda: (self._render(), GLib.SOURCE_REMOVE)[1])

        def work():
            try:
                with self.lock:
                    fn(*args)
            finally:
                GLib.idle_add(self._done)
        threading.Thread(target=work, daemon=True).start()

    def _done(self):
        self.busy = False
        self.gen += 1
        self.shape = None                 # force the redraw: busy has changed
        self.refresh()
        return GLib.SOURCE_REMOVE

    def _on_pick(self, name, active):
        """Two or more ticked: shared. One: plain output. None: refused, the
        box is greyed out before it comes to that."""
        wanted = [n for n in self.selected if n != name]
        if active:
            wanted.append(name)
        if not wanted or wanted == self.selected:
            self._show(force=True)
            return
        self.selected = wanted               # the ticks answer at once
        if len(wanted) >= 2:
            self._act(self._start, list(wanted))
        else:
            # Down to one: not sharing any more. The sound stays on the one
            # left rather than going back to whatever played before.
            self._act(self._collapse, wanted[0])

    def _on_volume(self, name, scale):
        if self._quiet:
            return
        self.touched[name] = time.monotonic()
        value = int(scale.get_value())
        # Dragging fires dozens of these: let the last one through every 60 ms.
        pending = getattr(self, "_vol", {})
        self._vol = pending
        first = name not in pending
        pending[name] = value
        if first:
            def send():
                v = pending.pop(name, None)
                if v is not None:
                    spawn("pactl", "set-sink-volume", name, f"{v}%")
                return GLib.SOURCE_REMOVE
            GLib.timeout_add(60, send)

    def _on_offset(self, o, spin):
        ms = int(spin.get_value())
        old = getattr(self, "_off", None)
        if old:
            GLib.source_remove(old)

        def send():
            self._off = None
            spawn("pactl", "set-port-latency-offset", o.card, o.port, str(ms * 1000))
            return GLib.SOURCE_REMOVE
        self._off = GLib.timeout_add(350, send)

    def _connect(self, mac):
        self.connecting.add(mac)
        self._show(force=True)

        def work():
            self._bt("connect", mac)
            GLib.idle_add(self._connected, mac)
        threading.Thread(target=work, daemon=True).start()

    def _connected(self, mac):
        self.connecting.discard(mac)
        self.gen += 1
        self.shape = None
        self.refresh()
        return GLib.SOURCE_REMOVE

    # The workers below run on a thread: no GTK in there.

    def _start(self, members):
        """Load the new combination under the free name, move the default onto
        it, then drop the old one: the music never loses its output."""
        if not members:
            return
        share, module = current_share()
        if share is None:
            out = pactl("get-default-sink")
            self.state["configured"] = configured_sink()
            self.state["before"] = out.stdout.strip() if out and out.returncode == 0 else None
            save_state(self.state)
        name = SINKS[1] if share == SINKS[0] else SINKS[0]
        desc = self.s["sink"].replace("'", "’")
        out = pactl("load-module", "module-combine-sink", f"sink_name={name}",
                    f"sink_properties=\"device.description='{desc}'\"",
                    "sinks=" + ",".join(members), "latency_compensate=true")
        if not out or out.returncode != 0:
            return
        pactl("set-default-sink", name)
        if module is not None:
            pactl("unload-module", str(module))

    def _stop(self):
        """Put WirePlumber's *choice* back the way it was, not the output that
        happened to be playing: re-choosing the same name changes nothing, and
        with no choice before, there is none after either, so priority (and a
        headset that connects later) still decides."""
        _share, module = current_share()
        before = self.state.get("configured")
        if before:
            pactl("set-default-sink", before)
        else:
            run("pw-metadata", "-d", "0", "default.configured.audio.sink", timeout=3)
        if module is not None:
            pactl("unload-module", str(module))

    def _alone(self, o):
        self._collapse(o.name)

    def _collapse(self, name):
        """Play on this one output, sharing or not. Back to the output that
        played before the share, it is the share being undone: WirePlumber's
        own choice is restored, not a new one pinned over it."""
        share, module = current_share()
        if share and name == self.state.get("before"):
            self._stop()
            return
        pactl("set-default-sink", name)
        if module is not None:
            pactl("unload-module", str(module))

    def _profile(self, o, profile):
        pactl("set-card-profile", o.card, profile)

    @staticmethod
    def _a2dp(card):
        """Back from hands-free (or from off) to music: the bare a2dp-sink
        lets PipeWire pick the best codec the headset offers."""
        cards = {c.get("name"): c for c in pactl_json("list", "cards")}
        profiles = (cards.get(card) or {}).get("profiles") or {}
        options = [p for p, v in profiles.items()
                   if p.startswith("a2dp-sink") and v.get("available", True)]
        if options:
            pactl("set-card-profile", card, "a2dp-sink" if "a2dp-sink" in options else options[0])

    def _audio_on(self, mac):
        self._a2dp("bluez_card." + mac.replace(":", "_"))

    @staticmethod
    def _bt(verb, mac):
        run("bluetoothctl", verb, mac, timeout=20)

    @staticmethod
    def _power():
        run("bluetoothctl", "power", "on", timeout=8)

    def reload_theme(self):
        """Called on SIGUSR1, once matugen has regenerated the palette."""
        Gtk.Settings.get_default().reset_property("gtk-theme-name")
        self._render()
        return GLib.SOURCE_REMOVE


class App(Adw.Application):
    """`HyprDuo.py` from the bar: a menu, gone when the focus leaves.
    `HyprDuo.py --pin` from Super+A: stays until the same key, or Esc.

    A second launch does not start a second process: GApplication hands its
    arguments to the one running, and this is where they land."""

    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def do_command_line(self, cmdline):
        pin = "--pin" in cmdline.get_arguments()[1:]
        win = self.props.active_window
        if win is None:
            win = Duo(self, pinned=pin)
            win.present()
            signal.signal(signal.SIGUSR1, lambda *_: GLib.idle_add(win.reload_theme))
        elif win.pinned:
            win.close()                   # the shortcut again: unlock and go
        elif pin:
            win.set_pinned(True)          # opened from the bar, locked from the keyboard
            win.present()
        elif win.leaving() or win.is_active():
            # Clicking the bar again: that click took the focus first, so the
            # popup is on its way out. Make it go now rather than come back.
            win.close()
        else:
            win.present()
        return 0


if __name__ == "__main__":
    # the real argv: run(None) hands GApplication nothing, and --pin never arrives
    App().run(sys.argv)
