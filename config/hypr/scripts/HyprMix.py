#!/usr/bin/env python3
"""HyprMix -- the sound mixer pages: outputs, microphones, applications.

Not a window of its own any more: HyprDuo's popup shows these pages as tabs
beside its Share tab, so the mixer and the share are one panel under the bar,
and switching between them is a tab, not a second window over the first.

  * Outputs and Microphones: one card per device -- volume up to 150 %, mute,
    make it the default, pick its port, and a live level meter.
  * Applications: every stream playing or recording -- its own volume and
    mute, and which output (or microphone) it goes through.

Everything goes through `pactl`, which pipewire-pulse answers. The host
forwards `pactl subscribe` events, so the pages follow the system rather
than polling it, and only while one of them is on screen.

Level meters: one `parec` per device, mono 16 kHz in 40 ms chunks, started
only for the page on screen and stopped when it is left. Reading an output
taps its monitor, which costs nothing; reading a microphone opens it, which
is the point of a microphone meter. Those streams carry this panel's id, so
they never show up in its own Applications page.

The pages are rebuilt only when the shape of things changes (a device or a
stream comes or goes, a default or a port changes). Volumes, mutes and
meters are updated in place, so a slider is never rebuilt under the finger
dragging it.

Run as a script, it opens HyprDuo on one of these pages:

  HyprMix.py                  Outputs, locked open (Super+Shift+A)
  HyprMix.py --page inputs    Microphones
"""

import json
import math
import os
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

# Tags this panel's own meter streams, so its Applications page skips them.
APP_ID = "dev.local.HyprMix"
LANG_FILE = os.path.expanduser("~/.config/hypr/scripts/.hyprsettings-lang")
SCRIPTS = os.path.dirname(os.path.realpath(__file__))

VOLUME_MAX = 150
METER_RATE = 16000
METER_CHUNK = METER_RATE * 2 * 40 // 1000      # 40 ms of s16 mono

# HyprDuo's combined output: shown, but its own streams into the real
# outputs are plumbing, not applications.
DUO_SINKS = ("hyprduo-a", "hyprduo-b")

G_HEAD = "\U000f02cb"
G_HEADSET = "\U000f02ce"
G_SPEAKER = "\U000f04c3"
G_LAPTOP = "\U000f0322"
G_SCREEN = "\U000f0379"
G_MIC = "\U000f036c"
G_SHARE = "\U000f0d38"
G_VOL = "\U000f057e"
G_MUTE = "\U000f0581"
G_MIC_OFF = "\U000f036d"
G_APP = "\U000f075a"

T = {
    "fr": {
        "title": "Mixeur",
        "outputs": "Sorties", "inputs": "Micros", "apps": "Applications",
        "default": "Par défaut", "make_default": "Par défaut",
        "make_default_tip": "Faire de cette sortie celle par défaut",
        "make_default_in": "Faire de ce micro celui par défaut",
        "mute": "Couper", "unmute": "Rétablir",
        "port": "Port", "unplugged": "débranché",
        "k_bt": "Bluetooth", "k_usb": "USB", "k_hdmi": "HDMI", "k_builtin": "Intégré",
        "k_virtual": "Virtuel", "k_shared": "Partage HyprDuo",
        "builtin_out": "Carte son intégrée", "builtin_in": "Micro intégré",
        "playing": "Lecture", "recording": "Enregistrement",
        "no_out": "Aucune sortie", "no_in": "Aucun micro",
        "no_in_sub": "Branche un micro ou un casque-micro",
        "no_play": "Aucune application ne joue de son",
        "no_rec": "Aucune application n'enregistre",
        "paused": "en pause",
        "share": "Partager le son…",
        "unknown_app": "Application",
    },
    "en": {
        "title": "Mixer",
        "outputs": "Outputs", "inputs": "Microphones", "apps": "Applications",
        "default": "Default", "make_default": "Make default",
        "make_default_tip": "Make this the default output",
        "make_default_in": "Make this the default microphone",
        "mute": "Mute", "unmute": "Unmute",
        "port": "Port", "unplugged": "unplugged",
        "k_bt": "Bluetooth", "k_usb": "USB", "k_hdmi": "HDMI", "k_builtin": "Built-in",
        "k_virtual": "Virtual", "k_shared": "HyprDuo share",
        "builtin_out": "Built-in audio", "builtin_in": "Built-in microphone",
        "playing": "Playing", "recording": "Recording",
        "no_out": "No output", "no_in": "No microphone",
        "no_in_sub": "Plug in a microphone or a headset",
        "no_play": "No application is playing sound",
        "no_rec": "No application is recording",
        "paused": "paused",
        "share": "Share the sound…",
        "unknown_app": "Application",
    },
}

CSS = b"""
.hm-root, .hm-root button, .hm-root label, .hm-root dropdown {
  font-family: "JetBrainsMono Nerd Font Propo", "JetBrains Mono", monospace;
  font-size: 12px;
}

/* bare classes lose to `.hm-root label`, hence the prefix on every label rule */
.hm-root .hm-sec { font-size: 10px; letter-spacing: 1.6px; opacity: 0.65; }
.hm-root .hm-name { font-weight: 700; font-size: 12.5px; }
.hm-root .hm-meta { font-size: 11px; opacity: 0.66; }
.hm-root .hm-icon { font-size: 18px; min-width: 24px; }
.hm-root .hm-value { font-size: 11px; min-width: 42px; }
.hm-root .hm-chip {
  font-size: 11px; padding: 2px 10px; border-radius: 999px;
  background: alpha(@accent_color, 0.20); color: @accent_color;
}

.hm-card {
  padding: 8px 10px; border-radius: 9px;
  background: alpha(currentColor, 0.045);
  border: 1px solid alpha(currentColor, 0.08);
}
.hm-card.hm-default {
  background: alpha(@accent_color, 0.08);
  border-color: alpha(@accent_color, 0.25);
}
.hm-default .hm-icon { color: @accent_color; }
.hm-card.hm-quiet { opacity: 0.6; }

.hm-root button.hm-act {
  min-height: 24px; padding: 0 10px; font-size: 11px;
  border-radius: 7px; background: none;
  border: 1px solid alpha(currentColor, 0.28); box-shadow: none;
}
.hm-root button.hm-act:hover { background: alpha(@accent_color, 0.16); }
.hm-root button.hm-round {
  min-width: 30px; min-height: 30px; padding: 0; border-radius: 999px;
  background: alpha(currentColor, 0.07); border: none; box-shadow: none;
}
.hm-root button.hm-round label { font-size: 15px; }
.hm-root button.hm-round:hover { background: alpha(@accent_color, 0.18); }
.hm-root button.hm-round.hm-muted { background: alpha(#f2777a, 0.22); color: #f2777a; }

.hm-root scale { padding: 0; margin: 0 2px; }
.hm-root scale trough { min-height: 5px; border-radius: 999px; }
.hm-root scale highlight { border-radius: 999px; }
.hm-root scale slider { min-width: 14px; min-height: 14px; margin: -5px; }
.hm-muted-card scale highlight { background: alpha(currentColor, 0.30); }

/* the meter: a thin line under the slider, accent while the signal is sane,
   amber near the top, red when it clips */
.hm-root levelbar trough { min-height: 3px; padding: 0; border: none;
  background: alpha(currentColor, 0.08); border-radius: 999px; }
.hm-root levelbar block { min-height: 3px; border-radius: 999px; border: none; }
.hm-root levelbar block.filled.low { background: @accent_color; }
.hm-root levelbar block.filled.high { background: #e8b339; }
.hm-root levelbar block.filled.full { background: #f2777a; }
.hm-root levelbar block.empty { background: transparent; }

.hm-root dropdown > button { min-height: 24px; padding: 0 8px; font-size: 11px; }
.hm-root .hm-empty { margin: 22px 16px; }
"""


# -- helpers ----------------------------------------------------------------

def lang():
    try:
        with open(LANG_FILE, encoding="utf-8") as fh:
            v = fh.read().strip()
            if v in T:
                return v
    except OSError:
        pass
    return "fr"


def pactl(*args, timeout=5):
    try:
        return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return None


def pactl_json(*args):
    out = pactl("-f", "json", *args)
    try:
        return json.loads(out.stdout) if out and out.returncode == 0 else []
    except ValueError:
        return []


def fire(*args):
    """A pactl command whose answer nobody waits for: volume while dragging."""
    try:
        subprocess.Popen(["pactl", *args], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        pass


def spawn(*argv):
    try:
        subprocess.Popen(argv, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def reach(app_id, action, *fallback):
    """Ask a resident app over D-Bus (5 ms); start it if it is not there."""
    try:
        if subprocess.run(["gapplication", "action", app_id, action],
                          capture_output=True, timeout=2).returncode == 0:
            return
    except (subprocess.SubprocessError, OSError):
        pass
    spawn(*fallback)


def percent(volume):
    try:
        return max(int(ch["value_percent"].rstrip("%")) for ch in volume.values())
    except (AttributeError, ValueError, KeyError):
        return 0


# -- the model --------------------------------------------------------------

class Device:
    """A sink or a source."""

    def __init__(self, raw, kind):
        props = raw.get("properties", {})
        self.kind = kind                         # "sink" / "source"
        self.index = raw.get("index")
        self.name = raw.get("name", "")
        self.label = raw.get("description") or self.name
        self.volume = percent(raw.get("volume", {}))
        self.mute = bool(raw.get("mute"))
        self.port = raw.get("active_port")
        self.ports = [(p.get("name"), p.get("description") or p.get("name"),
                       p.get("availability") != "not available")
                      for p in raw.get("ports") or []]
        api = props.get("device.api")
        ff = (props.get("device.form_factor") or "") + (props.get("device.icon_name") or "")
        self.codec = props.get("api.bluez5.codec")
        if self.name in DUO_SINKS:
            self.where, self.glyph = "shared", G_SHARE
        elif api == "bluez5":
            self.where = "bt"
            self.glyph = G_HEADSET if "headset" in ff else (
                G_SPEAKER if "speaker" in ff else G_HEAD)
        elif api == "alsa":
            ptype = ""
            for p in raw.get("ports") or []:
                if p.get("name") == self.port:
                    ptype = (p.get("type") or "").lower()
            if props.get("device.bus") == "usb":
                self.where = "usb"
            elif ptype in ("hdmi", "spdif") or "hdmi" in self.name:
                self.where = "hdmi"
            else:
                self.where = "builtin"
            if kind == "source":
                self.glyph = G_HEADSET if "head" in ff else G_MIC
            elif self.where == "hdmi":
                self.glyph = G_SCREEN
            elif "head" in ff or ptype == "headphones":
                self.glyph = G_HEAD
            else:
                self.glyph = G_LAPTOP if self.where == "builtin" else G_SPEAKER
        else:
            self.where = "virtual"
            self.glyph = G_MIC if kind == "source" else G_SPEAKER
        # The node to read a level from: an output's monitor, a microphone itself.
        self.tap = (raw.get("monitor_source") if kind == "sink" else self.name)

    def key(self):
        return (self.kind, self.name, self.label, self.port, tuple(self.ports),
                self.where, self.glyph, self.codec)


class Stream:
    """An application playing (sink-input) or recording (source-output)."""

    def __init__(self, raw, kind):
        props = raw.get("properties", {})
        self.kind = kind                         # "play" / "rec"
        self.index = raw.get("index")
        self.target = raw.get("sink") if kind == "play" else raw.get("source")
        self.volume = percent(raw.get("volume", {}))
        self.mute = bool(raw.get("mute"))
        self.corked = bool(raw.get("corked"))
        self.app = (props.get("application.name") or props.get("application.process.binary")
                    or props.get("node.name") or "")
        media = props.get("media.name") or ""
        self.media = "" if media == self.app else media
        self.icon = props.get("application.icon_name") or props.get("application.process.binary")
        self.has_volume = bool(raw.get("has_volume", True))

    def key(self):
        return (self.kind, self.index, self.target, self.app, self.media, self.corked, self.icon)


class Snapshot:
    def __init__(self):
        self.sinks, self.sources, self.playing, self.recording = [], [], [], []
        self.default_sink = self.default_source = None

    def key(self):
        return (tuple(d.key() for d in self.sinks), tuple(d.key() for d in self.sources),
                tuple(s.key() for s in self.playing), tuple(s.key() for s in self.recording),
                self.default_sink, self.default_source)


def snapshot():
    snap = Snapshot()
    snap.sinks = [Device(s, "sink") for s in pactl_json("list", "sinks")]
    snap.sources = [Device(s, "source") for s in pactl_json("list", "sources")
                    if (s.get("properties", {}).get("device.class") != "monitor"
                        and not s.get("name", "").endswith(".monitor"))]
    for raw in pactl_json("list", "sink-inputs"):
        props = raw.get("properties", {})
        if props.get("application.id") == APP_ID:
            continue
        if (props.get("node.name") or "").startswith("output.hyprduo"):
            continue                              # HyprDuo's plumbing
        snap.playing.append(Stream(raw, "play"))
    for raw in pactl_json("list", "source-outputs"):
        props = raw.get("properties", {})
        if props.get("application.id") == APP_ID:
            continue                              # our own meters
        snap.recording.append(Stream(raw, "rec"))
    for attr, cmd in (("default_sink", "get-default-sink"), ("default_source", "get-default-source")):
        out = pactl(cmd)
        setattr(snap, attr, out.stdout.strip() if out and out.returncode == 0 else None)
    order = {"shared": 0, "bt": 1, "usb": 2, "builtin": 3, "hdmi": 4, "virtual": 5}
    for devices in (snap.sinks, snap.sources):
        devices.sort(key=lambda d: (order.get(d.where, 9), d.label.lower()))
    snap.playing.sort(key=lambda s: (s.corked, s.app.lower()))
    snap.recording.sort(key=lambda s: s.app.lower())
    return snap


# -- level meters -----------------------------------------------------------

class Meter:
    """`parec` on one node, reporting a 0..1 level 25 times a second."""

    def __init__(self, node, on_level):
        self.on_level = on_level
        self.proc = None
        try:
            self.proc = subprocess.Popen(
                ["parec", "--raw", "--format=s16le", "--channels=1",
                 f"--rate={METER_RATE}", "--latency-msec=40", "-d", node,
                 f"--property=application.id={APP_ID}",
                 "--property=application.name=HyprMix",
                 "--property=media.name=level meter",
                 "--client-name=HyprMix"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        stream = self.proc.stdout
        while True:
            chunk = stream.read(METER_CHUNK)
            if not chunk:
                return
            peak = 0
            view = memoryview(chunk).cast("h") if len(chunk) % 2 == 0 else ()
            for sample in view[::4]:          # every 4th sample is plenty for a peak
                if sample > peak:
                    peak = sample
                elif -sample > peak:
                    peak = -sample
            # -60 dB .. 0 dB onto 0 .. 1: a meter in dB reads like an ear does
            level = 0.0 if peak == 0 else max(0.0, min(1.0, (20 * math.log10(peak / 32768) + 60) / 60))
            GLib.idle_add(self.on_level, level)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


# -- the panel --------------------------------------------------------------

_css_loaded = False


class MixerPanel:
    """The three mixer pages, for a host window to place where it likes.

    `widget(page)` gives a page's scroller; `set_active(page)` says which one
    is on screen (None: none, the window is hidden or on another tab), which
    is what starts and stops reading and metering. `poke()` is how the host
    passes on a `pactl subscribe` event; `on_resize` is called when a page's
    content changed size, for a host that fits its window to it."""

    PAGES = ("outputs", "inputs", "apps")
    MAX_HEIGHT = 560

    def __init__(self, on_resize=None):
        global _css_loaded
        self.s = T[lang()]
        self.on_resize = on_resize
        self.active = None
        self.snap = None
        self.shape = None
        self.widgets = {}            # id -> (scale, value label, mute button, row)
        self.meters = {}             # tap node -> Meter
        self.bars = {}               # tap node -> Gtk.LevelBar
        self.levels = {}             # tap node -> smoothed level
        self.touched = {}
        self.pending_vol = {}
        self._quiet = False
        self._probing = False
        self._again = False
        self._poke_id = None

        if not _css_loaded:
            provider = Gtk.CssProvider()
            provider.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            _css_loaded = True

        self.pages, self.scrollers = {}, {}
        for key in self.PAGES:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_margin_start(8); box.set_margin_end(8)
            box.set_margin_top(6); box.set_margin_bottom(8)
            scroller = Gtk.ScrolledWindow(child=box)
            scroller.add_css_class("hm-root")
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            # The page decides the popup's height, up to a point: past it, it scrolls.
            scroller.set_propagate_natural_height(True)
            scroller.set_max_content_height(self.MAX_HEIGHT)
            self.pages[key] = box
            self.scrollers[key] = scroller

    def widget(self, page):
        return self.scrollers[page]

    def set_active(self, page):
        self.active = page if page in self.PAGES else None
        if self.active:
            self.refresh()
        self._sync_meters()

    def stop(self):
        self.set_active(None)

    def poke(self):
        if self.active and self._poke_id is None:
            self._poke_id = GLib.timeout_add(150, self._poked)

    # -- reading -----------------------------------------------------------

    def _poked(self):
        self._poke_id = None
        if self.active:
            self.refresh()
        return GLib.SOURCE_REMOVE

    def refresh(self):
        if self._probing:
            self._again = True
            return GLib.SOURCE_REMOVE
        self._probing = True

        def work():
            snap = snapshot()
            GLib.idle_add(self._apply, snap)
        threading.Thread(target=work, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _apply(self, snap):
        self._probing = False
        self.snap = snap
        shape = snap.key()
        if shape != self.shape:
            self.shape = shape
            self._render()
        else:
            self._update_in_place()
        if self._again:
            self._again = False
            self.refresh()
        return GLib.SOURCE_REMOVE

    def _items(self):
        s = self.snap
        return ([("sink", d) for d in s.sinks] + [("source", d) for d in s.sources]
                + [("play", x) for x in s.playing] + [("rec", x) for x in s.recording])

    def _update_in_place(self):
        """Volumes and mutes, without rebuilding: someone may be dragging."""
        self._quiet = True
        now = time.monotonic()
        for kind, item in self._items():
            ident = (kind, item.index)
            w = self.widgets.get(ident)
            if not w:
                continue
            scale, value, mute, card = w
            if now - self.touched.get(ident, 0) > 1.5:
                scale.set_value(item.volume)
                value.set_label(f"{item.volume} %")
            self._paint_mute(mute, card, item.mute, kind)
        self._quiet = False

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

    def _clear(self, box):
        while (child := box.get_first_child()) is not None:
            box.remove(child)

    def _render(self):
        self.widgets = {}
        self.bars = {}
        for box in self.pages.values():
            self._clear(box)
        s = self.snap

        out = self.pages["outputs"]
        if s.sinks:
            for d in s.sinks:
                out.append(self._device_card(d, d.name == s.default_sink))
        else:
            out.append(self._empty(self.s["no_out"]))

        inp = self.pages["inputs"]
        if s.sources:
            for d in s.sources:
                inp.append(self._device_card(d, d.name == s.default_source))
        else:
            inp.append(self._empty(self.s["no_in"], self.s["no_in_sub"]))

        apps = self.pages["apps"]
        apps.append(self._section(self.s["playing"]))
        if s.playing:
            for x in s.playing:
                apps.append(self._stream_card(x))
        else:
            apps.append(self._empty(self.s["no_play"]))
        apps.append(self._section(self.s["recording"]))
        if s.recording:
            for x in s.recording:
                apps.append(self._stream_card(x))
        else:
            apps.append(self._empty(self.s["no_rec"]))

        self._sync_meters()
        if self.on_resize:
            self.on_resize()

    def _section(self, title):
        lbl = self._label(title.upper(), "hm-sec")
        lbl.set_margin_top(10); lbl.set_margin_start(2)
        return lbl

    def _empty(self, title, sub=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.add_css_class("hm-empty")
        box.append(self._label(title, "hm-name", xalign=0.5))
        if sub:
            box.append(self._label(sub, "hm-meta", xalign=0.5))
        return box

    def _name(self, d):
        """ "Ryzen HD Audio Controller Analog Stereo" names the chip, not where
        the sound comes out; the port, shown with it, says that."""
        if d.where == "builtin":
            return self.s["builtin_out" if d.kind == "sink" else "builtin_in"]
        return d.label

    def _device_card(self, d, is_default):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        card.add_css_class("hm-card")
        if is_default:
            card.add_css_class("hm-default")

        top = Gtk.Box(spacing=10)
        top.append(self._label(d.glyph, "hm-icon"))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        texts.append(self._label(self._name(d), "hm-name", ellipsize=True))
        texts.set_valign(Gtk.Align.CENTER)
        top.append(texts)

        if is_default:
            chip = self._label(self.s["default"], "hm-chip")
            chip.set_valign(Gtk.Align.CENTER)
            top.append(chip)
        else:
            make = Gtk.Button(label=self.s["make_default"], valign=Gtk.Align.CENTER)
            make.add_css_class("hm-act")
            make.set_tooltip_text(self.s["make_default_tip" if d.kind == "sink" else "make_default_in"])
            make.connect("clicked", lambda _b: self._default(d))
            top.append(make)
        card.append(top)

        kind = d.kind
        card.append(self._volume_row((kind, d.index), d, kind))

        bar = Gtk.LevelBar(min_value=0, max_value=1, mode=Gtk.LevelBarMode.CONTINUOUS)
        bar.add_offset_value("low", 0.80)
        bar.add_offset_value("high", 0.95)
        bar.add_offset_value("full", 1.0)
        bar.set_margin_start(44)
        bar.set_margin_end(52)
        if d.tap:
            self.bars[d.tap] = bar
        card.append(bar)

        if len(d.ports) > 1:
            names = [n for n, _desc, _a in d.ports]
            labels = [desc if avail else f"{desc} ({self.s['unplugged']})"
                      for _n, desc, avail in d.ports]
            row = Gtk.Box(spacing=8)
            row.set_margin_start(34)
            row.append(self._label(self.s["port"], "hm-meta"))
            drop = Gtk.DropDown.new_from_strings(labels)
            drop.set_hexpand(True)
            if d.port in names:
                drop.set_selected(names.index(d.port))
            drop.connect("notify::selected", lambda w, _p: self._port(d, names[w.get_selected()]))
            row.append(drop)
            card.append(row)
        return card

    def _volume_row(self, ident, item, kind):
        row = Gtk.Box(spacing=10)
        mute = Gtk.Button(valign=Gtk.Align.CENTER)
        mute.set_child(Gtk.Label())
        mute.add_css_class("hm-round")
        mute.connect("clicked", lambda _b: self._toggle_mute(kind, item))
        row.append(mute)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, VOLUME_MAX, 1)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        scale.set_value(item.volume)
        scale.add_mark(100, Gtk.PositionType.BOTTOM, None)
        scale.set_valign(Gtk.Align.CENTER)
        row.append(scale)

        value = self._label(f"{item.volume} %", "hm-value", xalign=1)
        row.append(value)
        scale.connect("value-changed", lambda w: self._on_volume(ident, kind, item, w, value))

        card_ref = row  # the card is set by the caller's parent; mute paints the row
        self.widgets[ident] = (scale, value, mute, card_ref)
        self._paint_mute(mute, card_ref, item.mute, kind)
        return row

    def _paint_mute(self, button, row, muted, kind):
        mic = kind in ("source", "rec")
        button.get_child().set_label((G_MIC_OFF if mic else G_MUTE) if muted
                                     else (G_MIC if mic else G_VOL))
        button.set_tooltip_text(self.s["unmute"] if muted else self.s["mute"])
        if muted:
            button.add_css_class("hm-muted")
            row.add_css_class("hm-muted-card")
        else:
            button.remove_css_class("hm-muted")
            row.remove_css_class("hm-muted-card")

    def _stream_card(self, x):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        card.add_css_class("hm-card")
        if x.corked:
            card.add_css_class("hm-quiet")

        top = Gtk.Box(spacing=10)
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        if x.icon and theme.has_icon(x.icon):
            icon = Gtk.Image.new_from_icon_name(x.icon)
            icon.set_pixel_size(22)
            icon.set_size_request(24, -1)
            top.append(icon)
        else:
            top.append(self._label(G_APP, "hm-icon"))

        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        texts.append(self._label(x.app or self.s["unknown_app"], "hm-name", ellipsize=True))
        meta = x.media
        if x.corked:
            meta = f"{meta}  ·  {self.s['paused']}" if meta else self.s["paused"]
        if meta:
            texts.append(self._label(meta, "hm-meta", ellipsize=True))
        top.append(texts)

        devices = self.snap.sinks if x.kind == "play" else self.snap.sources
        if len(devices) > 1:
            labels = [self._name(d) for d in devices]
            indexes = [d.index for d in devices]
            drop = Gtk.DropDown.new_from_strings(labels)
            drop.set_valign(Gtk.Align.CENTER)
            drop.set_size_request(128, -1)
            if x.target in indexes:
                drop.set_selected(indexes.index(x.target))
            drop.connect("notify::selected",
                         lambda w, _p: self._move(x, indexes[w.get_selected()]))
            top.append(drop)
        card.append(top)

        if x.has_volume:
            card.append(self._volume_row((x.kind, x.index), x, x.kind))
        return card

    # -- meters ------------------------------------------------------------

    def _sync_meters(self):
        """Meters only for the page on screen: a microphone meter opens the
        microphone, and nothing should listen while nobody is looking."""
        page = self.active
        if self.snap is None:
            page = None
        wanted = set()
        if page == "outputs":
            wanted = {d.tap for d in self.snap.sinks if d.tap}
        elif page == "inputs":
            wanted = {d.tap for d in self.snap.sources if d.tap}
        for node in list(self.meters):
            if node not in wanted:
                self.meters.pop(node).stop()
                self.levels.pop(node, None)
        for node in wanted:
            if node not in self.meters:
                self.meters[node] = Meter(node, lambda level, n=node: self._level(n, level))

    def _level(self, node, level):
        # Fast up, slow down: the eye reads peaks, not flicker.
        old = self.levels.get(node, 0.0)
        smooth = level if level > old else old * 0.82 + level * 0.18
        self.levels[node] = smooth
        bar = self.bars.get(node)
        if bar is not None:
            bar.set_value(smooth)
        return GLib.SOURCE_REMOVE

    # -- actions -----------------------------------------------------------

    def _on_volume(self, ident, kind, item, scale, value):
        if self._quiet:
            return
        v = int(scale.get_value())
        value.set_label(f"{v} %")
        self.touched[ident] = time.monotonic()
        first = ident not in self.pending_vol
        self.pending_vol[ident] = v
        if first:
            def send():
                vol = self.pending_vol.pop(ident, None)
                if vol is not None:
                    verb = {"sink": "set-sink-volume", "source": "set-source-volume",
                            "play": "set-sink-input-volume",
                            "rec": "set-source-output-volume"}[kind]
                    target = item.name if kind in ("sink", "source") else str(item.index)
                    fire(verb, target, f"{vol}%")
                return GLib.SOURCE_REMOVE
            GLib.timeout_add(50, send)

    def _toggle_mute(self, kind, item):
        verb = {"sink": "set-sink-mute", "source": "set-source-mute",
                "play": "set-sink-input-mute", "rec": "set-source-output-mute"}[kind]
        target = item.name if kind in ("sink", "source") else str(item.index)
        item.mute = not item.mute
        w = self.widgets.get((kind, item.index))
        if w:
            self._paint_mute(w[2], w[3], item.mute, kind)
        fire(verb, target, "toggle")

    def _default(self, d):
        """An explicit choice: WirePlumber is told to remember it."""
        fire("set-default-sink" if d.kind == "sink" else "set-default-source", d.name)

    def _port(self, d, port):
        if port != d.port:
            fire("set-sink-port" if d.kind == "sink" else "set-source-port", d.name, port)

    def _move(self, x, target):
        if target != x.target:
            fire("move-sink-input" if x.kind == "play" else "move-source-output",
                 str(x.index), str(target))

    def reload_theme(self):
        Gtk.Settings.get_default().reset_property("gtk-theme-name")
        self.shape = None
        if self.snap:
            self._apply(self.snap)
        return GLib.SOURCE_REMOVE


def main():
    """Open HyprDuo's popup on a mixer page: a 5 ms message to the resident
    popup, or HyprDuo itself when it is not running."""
    args = sys.argv[1:]
    page = args[args.index("--page") + 1] if "--page" in args and \
        args.index("--page") + 1 < len(args) else "outputs"
    duo = os.path.join(SCRIPTS, "HyprDuo.py")
    if page == "inputs":
        reach("dev.local.HyprDuo", "mic", duo, "--tab", "inputs")
    else:
        reach("dev.local.HyprDuo", "mixer-pinned", duo, "--pin", "--tab", page)


if __name__ == "__main__":
    main()
