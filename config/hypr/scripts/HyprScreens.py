#!/usr/bin/env python3
"""HyprScreens -- arrange and set up the monitors (bilingual FR / EN).

Replaces nwg-displays, with the desktop's own look. A canvas to drag the
screens into place (edges snap together), and for the one selected: on/off,
resolution, refresh rate, scale, rotation, variable refresh, mirroring.

How a change lands, so the next reader does not have to dig:

  * Apply sends each monitor to Hyprland live, as `hl.monitor{...}` through
    `hyprctl eval` (the Lua config refuses the legacy `keyword monitor`).
  * Then a dialog asks to keep it, counting down. No answer -- a screen gone
    black, a mode the panel cannot show -- and the previous setup comes back
    by itself. Only a kept setup is written to disk.
  * It is written to ~/.config/hypr/monitors.lua, which hyprland.lua loads on
    every reload. Screens unplugged at that moment keep their entries: the
    layout of a desk monitor survives being saved from the train.

Scales are offered only where they divide the resolution evenly: Hyprland
silently picks another one otherwise, and the screen would not be the size
the canvas shows.

Like the other panels it has no palette of its own: it inherits GTK's, which
matugen regenerates on every wallpaper change. SIGUSR1 reloads the theme.
"""

import json
import math
import os
import re
import signal
import subprocess
import sys
import warnings

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402

APP_ID = "dev.local.HyprScreens"
LANG_FILE = os.path.expanduser("~/.config/hypr/scripts/.hyprsettings-lang")
MONITORS = os.path.expanduser("~/.config/hypr/monitors.lua")

CONFIRM_SECONDS = 15
SNAP = 48                      # logical px within which edges snap together
SCALES = (1.0, 1.25, 4 / 3, 1.5, 1.6, 5 / 3, 1.75, 2.0, 2.25, 2.5, 3.0)

T = {
    "fr": {
        "title": "Écrans",
        "apply": "Appliquer", "reset": "Annuler les changements",
        "enabled": "Activé", "enabled_sub": "Le dernier écran allumé ne peut pas être éteint",
        "resolution": "Résolution", "rate": "Fréquence", "scale": "Échelle",
        "rotation": "Rotation", "vrr": "Fréquence variable", "mirror": "Recopie de",
        "position": "Position",
        "rot": ["Normale", "90°", "180°", "270°"],
        "vrr_opts": ["Désactivée", "Activée", "Plein écran seulement"],
        "none": "Aucune",
        "logical": "{w} × {h} une fois mis à l'échelle",
        "keep_q": "Garder ces réglages ?",
        "keep_body": "Retour aux réglages précédents dans {n} s.",
        "keep": "Garder", "revert": "Revenir",
        "saved": "Enregistré dans monitors.lua",
        "reverted": "Réglages précédents rétablis",
        "drag": "Fais glisser les écrans pour les placer ; leurs bords s'aimantent.",
        "off": "éteint",
        "failed": "Hyprland n'a pas accepté : {err}",
        "substituted": "{name} : Hyprland a choisi {got} au lieu de {want}.",
    },
    "en": {
        "title": "Displays",
        "apply": "Apply", "reset": "Discard changes",
        "enabled": "Enabled", "enabled_sub": "The last screen on cannot be turned off",
        "resolution": "Resolution", "rate": "Refresh rate", "scale": "Scale",
        "rotation": "Rotation", "vrr": "Variable refresh", "mirror": "Mirror of",
        "position": "Position",
        "rot": ["Normal", "90°", "180°", "270°"],
        "vrr_opts": ["Off", "On", "Fullscreen only"],
        "none": "None",
        "logical": "{w} × {h} once scaled",
        "keep_q": "Keep these settings?",
        "keep_body": "Back to the previous settings in {n} s.",
        "keep": "Keep", "revert": "Revert",
        "saved": "Saved to monitors.lua",
        "reverted": "Previous settings restored",
        "drag": "Drag the screens into place; their edges snap together.",
        "off": "off",
        "failed": "Hyprland refused it: {err}",
        "substituted": "{name}: Hyprland chose {got} instead of {want}.",
    },
}

CSS = b"""
window.hs-root, window.hs-root.background { background: alpha(@window_bg_color, 0.97); }
.hs-root, .hs-root button, .hs-root label, .hs-root dropdown, .hs-root spinbutton {
  font-family: "JetBrainsMono Nerd Font Propo", "JetBrains Mono", monospace;
  font-size: 12px;
}
.hs-root headerbar { background: transparent; box-shadow: none; }
.hs-root .hs-sec { font-size: 10px; letter-spacing: 1.6px; opacity: 0.65; }
.hs-root .hs-name { font-weight: 700; font-size: 13px; }
.hs-root .hs-meta { font-size: 11px; opacity: 0.66; }
.hs-canvas {
  border-radius: 10px;
  background: alpha(currentColor, 0.04);
  border: 1px solid alpha(currentColor, 0.08);
}
.hs-card {
  padding: 4px 14px; border-radius: 10px;
  background: alpha(currentColor, 0.045);
  border: 1px solid alpha(currentColor, 0.08);
}
.hs-row { min-height: 40px; }
.hs-row + .hs-row { border-top: 1px solid alpha(currentColor, 0.07); }
.hs-root dropdown > button { min-height: 26px; padding: 0 8px; }
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


def hyprctl(*args, timeout=5):
    try:
        return subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return None


def fmt_num(x):
    """2.0 -> 2, 1.333333 -> 1.333333: what a person would write."""
    return f"{x:.6f}".rstrip("0").rstrip(".")


def fmt_rate(rate):
    return f"{rate:.2f}"


def even(size, scale):
    """True when `scale` cuts `size` into whole logical pixels."""
    v = size / scale
    return abs(v - round(v)) < 0.01


# -- the model --------------------------------------------------------------

class Monitor:
    def __init__(self, raw):
        self.name = raw["name"]
        self.desc = " ".join(x for x in (raw.get("make"), raw.get("model")) if x) \
            or raw.get("description") or self.name
        self.enabled = not raw.get("disabled", False)
        modes = []
        for m in raw.get("availableModes", []):
            match = re.match(r"(\d+)x(\d+)@([\d.]+)", m)
            if match:
                mode = (int(match.group(1)), int(match.group(2)), float(match.group(3)))
                if mode not in modes:
                    modes.append(mode)
        self.modes = modes
        self.width, self.height = raw.get("width", 0), raw.get("height", 0)
        self.rate = round(float(raw.get("refreshRate", 60.0)), 2)
        self.scale = float(raw.get("scale", 1.0))
        self.transform = int(raw.get("transform", 0)) % 4
        self.vrr = 1 if raw.get("vrr") else 0
        self.x, self.y = raw.get("x", 0), raw.get("y", 0)
        mirror = raw.get("mirrorOf") or "none"
        self.mirror = None if mirror in ("none", "") else mirror
        if (self.width, self.height) == (0, 0) and modes:   # a disabled one reports nothing
            self.width, self.height, self.rate = modes[0]

    def clone(self):
        other = Monitor.__new__(Monitor)
        other.__dict__ = dict(self.__dict__)
        other.modes = list(self.modes)
        return other

    def logical(self):
        w, h = self.width / self.scale, self.height / self.scale
        if self.transform % 2:
            w, h = h, w
        return round(w), round(h)

    def resolutions(self):
        seen = []
        for w, h, _r in self.modes:
            if (w, h) not in seen:
                seen.append((w, h))
        if (self.width, self.height) not in seen:
            seen.insert(0, (self.width, self.height))
        return seen

    def rates(self):
        rates = sorted({r for w, h, r in self.modes if (w, h) == (self.width, self.height)},
                       reverse=True)
        return rates or [self.rate]

    def scales(self):
        found = [s for s in SCALES if even(self.width, s) and even(self.height, s)]
        if not any(abs(s - self.scale) < 0.001 for s in found):
            found.append(self.scale)
        return sorted(found)

    def lua(self):
        """This monitor as Hyprland's Lua config wants it."""
        if not self.enabled:
            return f'hl.monitor({{ output = "{self.name}", disabled = true }})'
        parts = [f'output = "{self.name}"',
                 f'mode = "{self.width}x{self.height}@{fmt_rate(self.rate)}"',
                 f'position = "{self.x}x{self.y}"',
                 f"scale = {fmt_num(self.scale)}",
                 f"transform = {self.transform}",
                 f"vrr = {self.vrr}"]
        if self.mirror:
            parts.append(f'mirror = "{self.mirror}"')
        return "hl.monitor({ " + ", ".join(parts) + " })"

    def key(self):
        return (self.name, self.enabled, self.width, self.height, self.rate,
                round(self.scale, 4), self.transform, self.vrr, self.x, self.y, self.mirror)


def read_monitors():
    out = hyprctl("monitors", "all", "-j")
    try:
        return [Monitor(m) for m in json.loads(out.stdout)] if out else []
    except (ValueError, KeyError):
        return []


def describe(m):
    return f"{m.width}×{m.height} @ {m.rate:g} Hz, {round(m.scale * 100)} %"


def substitutions(wanted, live):
    """What Hyprland set differently from what was asked. It does not refuse
    a mode it cannot drive: it answers ok and falls back to another one."""
    notes = []
    by_name = {m.name: m for m in live}
    for want in wanted:
        got = by_name.get(want.name)
        if not want.enabled or got is None or not got.enabled:
            continue
        if ((got.width, got.height) != (want.width, want.height)
                or abs(got.rate - want.rate) > 0.6
                or abs(got.scale - want.scale) > 0.01
                or got.transform != want.transform):
            notes.append((want.name, describe(got), describe(want)))
    return notes


def apply_live(monitors):
    """Send the whole set to Hyprland. Enabled screens first: turning one off
    before another is on could leave nothing to show the dialog on."""
    order = sorted(monitors, key=lambda m: not m.enabled)
    errors = []
    for m in order:
        chunk = (f"local ok, err = pcall(hl.monitor, {m.lua()[len('hl.monitor('):-1]}) "
                 f"if not ok then error(err) end")
        out = hyprctl("eval", chunk)
        text = (out.stdout + out.stderr).strip() if out else "hyprctl failed"
        if text != "ok":
            errors.append(f"{m.name}: {text}")
    return errors


BLOCK = re.compile(r"hl\.monitor\(\s*\{(.*?)\}\s*\)", re.S)
OUTPUT = re.compile(r'output\s*=\s*"([^"]+)"')


def save(monitors):
    """monitors.lua: the connected screens as set, plus whatever the file
    already said about screens that are not plugged in right now."""
    kept = []
    try:
        with open(MONITORS, encoding="utf-8") as fh:
            old = fh.read()
        names = {m.name for m in monitors}
        for block in BLOCK.finditer(old):
            match = OUTPUT.search(block.group(1))
            if match and match.group(1) not in names:
                body = " ".join(line.strip() for line in block.group(1).strip().splitlines())
                kept.append("hl.monitor({ " + body.rstrip(",") + " })")
    except OSError:
        pass
    lines = ["-- Written by HyprScreens; hyprland.lua loads it on every reload.",
             "-- Edit it from the app: a hand-made change survives only until the next save.",
             ""]
    lines += [m.lua() for m in monitors]
    if kept:
        lines += ["", "-- not plugged in at the last save, kept as they were"] + kept
    tmp = MONITORS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, MONITORS)


# -- the canvas -------------------------------------------------------------

class Canvas(Gtk.DrawingArea):
    """The monitors to scale, draggable; edges snap to the other screens'."""

    def __init__(self, window):
        super().__init__()
        self.win = window
        self.add_css_class("hs-canvas")
        self.set_content_height(230)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)
        self.view = (1.0, 0.0, 0.0)          # factor, offset x, offset y
        self.dragging = None
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._begin)
        drag.connect("drag-update", self._update)
        drag.connect("drag-end", self._end)
        self.add_controller(drag)

    def _rects(self):
        out = []
        for m in self.win.monitors:
            if not m.enabled or m.mirror:
                continue
            w, h = m.logical()
            out.append((m, m.x, m.y, w, h))
        return out

    def _fit(self, width, height):
        rects = self._rects()
        if not rects:
            return 1.0, 0.0, 0.0
        x0 = min(r[1] for r in rects); y0 = min(r[2] for r in rects)
        x1 = max(r[1] + r[3] for r in rects); y1 = max(r[2] + r[4] for r in rects)
        pad = 28
        factor = min((width - 2 * pad) / max(1, x1 - x0), (height - 2 * pad) / max(1, y1 - y0))
        factor = min(factor, 0.25)
        ox = (width - (x1 - x0) * factor) / 2 - x0 * factor
        oy = (height - (y1 - y0) * factor) / 2 - y0 * factor
        return factor, ox, oy

    def _draw(self, _area, cr, width, height):
        if self.dragging is None:
            self.view = self._fit(width, height)
        f, ox, oy = self.view
        fg = self.get_color()
        # The palette's accent is a CSS named colour (matugen's colors.css);
        # lookup_color is the only way to read one, deprecated or not.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ok, accent = self.get_style_context().lookup_color("accent_color")
        if not ok:
            accent = fg
        for m, x, y, w, h in self._rects():
            rx, ry, rw, rh = ox + x * f, oy + y * f, w * f, h * f
            selected = m is self.win.selected
            self._round(cr, rx + 1, ry + 1, rw - 2, rh - 2, 8)
            colour = accent if selected else fg
            cr.set_source_rgba(colour.red, colour.green, colour.blue, 0.22 if selected else 0.08)
            cr.fill_preserve()
            cr.set_source_rgba(colour.red, colour.green, colour.blue, 0.9 if selected else 0.35)
            cr.set_line_width(2 if selected else 1)
            cr.stroke()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.95)
            self._text(cr, m.name, rx + rw / 2, ry + rh / 2 - 8, 13, bold=True)
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
            self._text(cr, f"{m.width}×{m.height}", rx + rw / 2, ry + rh / 2 + 10, 11)

    @staticmethod
    def _round(cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _text(self, cr, text, cx, cy, size, bold=False):
        layout = self.create_pango_layout(text)
        desc = Pango.FontDescription.from_string(
            f"JetBrainsMono Nerd Font Propo {'Bold ' if bold else ''}{size}px")
        layout.set_font_description(desc)
        tw, th = layout.get_pixel_size()
        cr.move_to(cx - tw / 2, cy - th / 2)
        PangoCairo.show_layout(cr, layout)

    def _hit(self, px, py):
        f, ox, oy = self.view
        for m, x, y, w, h in reversed(self._rects()):
            if ox + x * f <= px <= ox + (x + w) * f and oy + y * f <= py <= oy + (y + h) * f:
                return m
        return None

    def _begin(self, _g, px, py):
        m = self._hit(px, py)
        if m is None:
            self.dragging = None
            return
        self.win.select(m)
        self.dragging = (m, m.x, m.y)

    def _update(self, _g, dx, dy):
        if not self.dragging:
            return
        m, x0, y0 = self.dragging
        f = self.view[0]
        m.x, m.y = round(x0 + dx / f), round(y0 + dy / f)
        self.queue_draw()

    def _end(self, _g, _dx, _dy):
        if not self.dragging:
            return
        m = self.dragging[0]
        self._snap(m)
        self.dragging = None
        self.win.changed(positions_only=True)
        self.queue_draw()

    def _snap(self, m):
        """Glue an edge to the nearest edge of another screen, when close."""
        w, h = m.logical()
        best_x = best_y = None
        for other, x, y, ow, oh in self._rects():
            if other is m:
                continue
            for target in (x - w, x + ow, x, x + ow - w):        # beside, or aligned
                if abs(m.x - target) <= SNAP and (best_x is None or abs(m.x - target) < abs(m.x - best_x)):
                    best_x = target
            for target in (y - h, y + oh, y, y + oh - h):
                if abs(m.y - target) <= SNAP and (best_y is None or abs(m.y - target) < abs(m.y - best_y)):
                    best_y = target
        if best_x is not None:
            m.x = best_x
        if best_y is not None:
            m.y = best_y


# -- the window -------------------------------------------------------------

class Screens(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, default_width=720, default_height=640)
        self.s = T[lang()]
        self.set_title(self.s["title"])
        self.add_css_class("hs-root")

        self.live = read_monitors()                 # what Hyprland has now
        self.monitors = [m.clone() for m in self.live]
        self.selected = next((m for m in self.monitors if m.enabled), None) \
            or (self.monitors[0] if self.monitors else None)
        self._quiet = False

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        header = Adw.HeaderBar()
        self.apply_btn = Gtk.Button(label=self.s["apply"])
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.connect("clicked", lambda _b: self.apply())
        header.pack_end(self.apply_btn)
        self.reset_btn = Gtk.Button(icon_name="edit-undo-symbolic")
        self.reset_btn.set_tooltip_text(self.s["reset"])
        self.reset_btn.connect("clicked", lambda _b: self.reset())
        header.pack_start(self.reset_btn)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_margin_start(16); body.set_margin_end(16)
        body.set_margin_top(4); body.set_margin_bottom(16)
        self.canvas = Canvas(self)
        body.append(self.canvas)
        hint = Gtk.Label(label=self.s["drag"], xalign=0)
        hint.add_css_class("hs-meta")
        body.append(hint)
        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        body.append(self.panel)

        scroller = Gtk.ScrolledWindow(child=body, vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.toasts = Adw.ToastOverlay(child=scroller)
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self.toasts)
        self.set_content(view)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        self.build_panel()
        self.sync_buttons()

    def _on_key(self, _c, keyval, _kc, _st):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return Gdk.EVENT_STOP
        return Gdk.EVENT_PROPAGATE

    # -- state -------------------------------------------------------------

    def dirty(self):
        return [m.key() for m in self.monitors] != [m.key() for m in self.live]

    def sync_buttons(self):
        d = self.dirty()
        self.apply_btn.set_sensitive(d)
        self.reset_btn.set_sensitive(d)

    def select(self, m):
        if m is not self.selected:
            self.selected = m
            self.build_panel()
        self.canvas.queue_draw()

    def changed(self, positions_only=False):
        if positions_only:
            self._quiet = True
            if self.selected:
                self.spin_x.set_value(self.selected.x)
                self.spin_y.set_value(self.selected.y)
            self._quiet = False
        else:
            self.build_panel()
        self.canvas.queue_draw()
        self.sync_buttons()

    def reset(self):
        name = self.selected.name if self.selected else None
        self.monitors = [m.clone() for m in self.live]
        self.selected = next((m for m in self.monitors if m.name == name), None) \
            or (self.monitors[0] if self.monitors else None)
        self.changed()

    # -- the settings of the selected screen --------------------------------

    def _row(self, title, control, subtitle=None):
        row = Gtk.Box(spacing=12)
        row.add_css_class("hs-row")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        texts.append(Gtk.Label(label=title, xalign=0))
        if subtitle:
            sub = Gtk.Label(label=subtitle, xalign=0)
            sub.add_css_class("hs-meta")
            texts.append(sub)
        row.append(texts)
        control.set_valign(Gtk.Align.CENTER)
        row.append(control)
        return row

    def _drop(self, labels, selected, on_pick, width=220):
        drop = Gtk.DropDown.new_from_strings(labels)
        drop.set_size_request(width, -1)
        drop.set_selected(max(0, selected))
        drop.connect("notify::selected", lambda w, _p: None if self._quiet else on_pick(w.get_selected()))
        return drop

    def build_panel(self):
        self._quiet = True
        while (child := self.panel.get_first_child()) is not None:
            self.panel.remove(child)
        m = self.selected
        if m is None:
            self._quiet = False
            return

        head = Gtk.Box(spacing=10)
        name = Gtk.Label(label=m.name, xalign=0)
        name.add_css_class("hs-name")
        head.append(name)
        desc = Gtk.Label(label=m.desc, xalign=0, hexpand=True)
        desc.add_css_class("hs-meta")
        desc.set_ellipsize(Pango.EllipsizeMode.END)
        head.append(desc)
        lw, lh = m.logical()
        logical = Gtk.Label(label=self.s["logical"].format(w=lw, h=lh) if m.enabled else self.s["off"])
        logical.add_css_class("hs-meta")
        head.append(logical)
        self.panel.append(head)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("hs-card")

        others_on = [o for o in self.monitors if o is not m and o.enabled]
        switch = Gtk.Switch(active=m.enabled)
        switch.set_sensitive(bool(others_on) or not m.enabled)
        switch.connect("notify::active", lambda w, _p: self._set(m, "enabled", w.get_active()))
        card.append(self._row(self.s["enabled"], switch,
                              None if others_on else self.s["enabled_sub"]))

        if m.enabled:
            res = m.resolutions()
            current = res.index((m.width, m.height)) if (m.width, m.height) in res else 0
            card.append(self._row(self.s["resolution"], self._drop(
                [f"{w} × {h}" for w, h in res], current, lambda i: self._resolution(m, res[i]))))

            rates = m.rates()
            near = min(range(len(rates)), key=lambda i: abs(rates[i] - m.rate))
            card.append(self._row(self.s["rate"], self._drop(
                [f"{r:g} Hz" for r in rates], near, lambda i: self._set(m, "rate", rates[i]))))

            scales = m.scales()
            near = min(range(len(scales)), key=lambda i: abs(scales[i] - m.scale))
            card.append(self._row(self.s["scale"], self._drop(
                [f"{round(s * 100)} %" for s in scales], near,
                lambda i: self._set(m, "scale", scales[i]))))

            card.append(self._row(self.s["rotation"], self._drop(
                self.s["rot"], m.transform, lambda i: self._set(m, "transform", i))))

            card.append(self._row(self.s["vrr"], self._drop(
                self.s["vrr_opts"], m.vrr, lambda i: self._set(m, "vrr", i))))

            others = [o.name for o in self.monitors if o is not m and o.enabled and not o.mirror]
            if others:
                options = [self.s["none"]] + others
                current = options.index(m.mirror) if m.mirror in options else 0
                card.append(self._row(self.s["mirror"], self._drop(
                    options, current, lambda i: self._set(m, "mirror", None if i == 0 else options[i]))))

            pos = Gtk.Box(spacing=6)
            self.spin_x = Gtk.SpinButton.new_with_range(-20000, 20000, 1)
            self.spin_y = Gtk.SpinButton.new_with_range(-20000, 20000, 1)
            self.spin_x.set_value(m.x)
            self.spin_y.set_value(m.y)
            self.spin_x.connect("value-changed", lambda w: self._move(m, x=int(w.get_value())))
            self.spin_y.connect("value-changed", lambda w: self._move(m, y=int(w.get_value())))
            pos.append(self.spin_x)
            pos.append(Gtk.Label(label="×"))
            pos.append(self.spin_y)
            card.append(self._row(self.s["position"], pos))

        self.panel.append(card)
        self._quiet = False

    def _set(self, m, attr, value):
        if self._quiet:
            return
        setattr(m, attr, value)
        if attr == "scale" or attr == "transform":
            self._tidy(m)
        self.changed()

    def _resolution(self, m, size):
        m.width, m.height = size
        rates = m.rates()
        m.rate = min(rates, key=lambda r: abs(r - m.rate))
        if not (even(m.width, m.scale) and even(m.height, m.scale)):
            m.scale = 1.0          # the old scale does not divide the new size
        self._tidy(m)
        self.changed()

    def _move(self, m, x=None, y=None):
        if self._quiet:
            return
        if x is not None:
            m.x = x
        if y is not None:
            m.y = y
        self.canvas.queue_draw()
        self.sync_buttons()

    def _tidy(self, m):
        """A screen that grew or shrank must not now overlap its neighbours:
        the ones to its right and below are pushed along, the way they were."""
        w, h = m.logical()
        for o in self.monitors:
            if o is m or not o.enabled or o.mirror:
                continue
            ow, oh = o.logical()
            overlap_y = o.y < m.y + h and m.y < o.y + oh
            overlap_x = o.x < m.x + w and m.x < o.x + ow
            if overlap_x and overlap_y:
                if o.x >= m.x:
                    o.x = m.x + w
                elif o.y >= m.y:
                    o.y = m.y + h

    # -- apply, confirm, keep or revert --------------------------------------

    def apply(self):
        # Positions are sent as they are, never shifted back to 0,0: a screen
        # unplugged right now keeps its place in monitors.lua, and moving the
        # plugged ones alone would land them on top of it next time.
        previous = [m.clone() for m in self.live]
        errors = apply_live(self.monitors)
        if errors:
            apply_live(previous)
            self.toasts.add_toast(Adw.Toast(title=self.s["failed"].format(err=errors[0]), timeout=6))
            return
        GLib.timeout_add(600, self._confirm, previous)   # let the mode settle before reading it back

    def _confirm(self, previous):
        notes = substitutions(self.monitors, read_monitors())
        prefix = "".join(self.s["substituted"].format(name=n, got=g, want=w) + "\n\n"
                         for n, g, w in notes)
        dialog = Adw.AlertDialog(heading=self.s["keep_q"],
                                 body=prefix + self.s["keep_body"].format(n=CONFIRM_SECONDS))
        dialog.add_response("revert", self.s["revert"])
        dialog.add_response("keep", self.s["keep"])
        dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("revert")
        dialog.set_close_response("revert")
        left = [CONFIRM_SECONDS]
        done = [False]

        def tick():
            left[0] -= 1
            if left[0] <= 0:
                answered(dialog, "revert")           # time is up: nobody said keep
                dialog.force_close()
                return GLib.SOURCE_REMOVE
            dialog.set_body(prefix + self.s["keep_body"].format(n=left[0]))
            return GLib.SOURCE_CONTINUE
        timer = GLib.timeout_add_seconds(1, tick)

        def answered(_d, response):
            # Once only: closing the dialog emits its close response too, and
            # a "keep" followed by that "revert" would undo what was just kept.
            if done[0]:
                return
            done[0] = True
            if left[0] > 0:
                GLib.source_remove(timer)
            if response == "keep":
                save(self.monitors)
                self.live = read_monitors()
                self.toasts.add_toast(Adw.Toast(title=self.s["saved"], timeout=3))
            else:
                apply_live(previous)
                self.live = read_monitors()
                self.toasts.add_toast(Adw.Toast(title=self.s["reverted"], timeout=3))
            name = self.selected.name if self.selected else None
            self.monitors = [m.clone() for m in self.live]
            self.selected = next((m for m in self.monitors if m.name == name), None) \
                or (self.monitors[0] if self.monitors else None)
            self.changed()
        dialog.connect("response", answered)
        dialog.present(self)
        return GLib.SOURCE_REMOVE

    def reload_theme(self):
        Gtk.Settings.get_default().reset_property("gtk-theme-name")
        self.canvas.queue_draw()
        return GLib.SOURCE_REMOVE


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def do_command_line(self, _cmdline):
        win = self.props.active_window
        if win is None:
            win = Screens(self)
            signal.signal(signal.SIGUSR1, lambda *_: GLib.idle_add(win.reload_theme))
        win.present()
        return 0


if __name__ == "__main__":
    App().run(sys.argv)
