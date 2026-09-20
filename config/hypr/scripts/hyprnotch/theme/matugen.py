"""Bridge between matugen and the notch.

No colour is hard-coded. We re-read the file matugen already generates for
waybar -- it holds the complete Material You palette -- and concatenate it in
front of our own stylesheet. When the wallpaper changes, matugen rewrites the
file, the monitor sees it, and the theme follows.
"""

import os
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, Gtk  # noqa: E402

from . import waybar  # noqa: E402

DEFINE = re.compile(r"@define-color\s+([a-z0-9_]+)\s+([^;]+);")

# Brings player logos down to the height of waybar's icons.
GLYPH_RATIO = 0.95

# Measured gap between the size waybar declares and the one it actually draws:
# cap height compared against the pixel on the bar.
BAR_SCALE = 0.782

# Minimal fallback if matugen has never run: neutral greys, never an invented
# accent colour.
FALLBACK = {
    "background": "#141414", "surface": "#141414",
    "surface_container": "#1e1e1e", "surface_container_high": "#282828",
    "on_surface": "#e6e6e6", "on_surface_variant": "#b4b4b4",
    "outline": "#8a8a8a", "outline_variant": "#3a3a3a",
    "primary": "#d0bcff", "on_primary": "#20124a",
    "secondary": "#ccc2dc", "tertiary": "#efb8c8",
    # Without this entry, @error is defined nowhere when matugen has never run,
    # and GTK rejects THE WHOLE SHEET, not just the one rule.
    "error": "#ffb4ab",
}

STYLE = """
window, window.background {{ background: transparent; }}
/* The theme puts an opaque background on scrolledwindow and viewport; it showed
   through the shell at rest. */
scrolledwindow, viewport, stack {{ background: transparent; }}

.nk-root, .nk-root label, .nk-root button {{
  font-family: "JetBrainsMono Nerd Font Propo", "JetBrains Mono", monospace;
  color: @on_surface;
}}

/* The shell. The only element that draws a background: everything else sits on
   top of it, which keeps the rounded corners clean during the animation. */
.nk-shell {{
  background: alpha(@background, {opacity});
  border: 1px solid alpha(@outline, 0.22);
  border-radius: {radius}px;
  /* The shell fades out rather than vanishing when the pill
     becomes invisible again. */
  transition: background-color 140ms ease-out, border-color 140ms ease-out;
}}

/* At rest, with nothing playing: the shell draws nothing, but the surface is
   still there -- it can still be hovered to open the panel. */
.nk-shell.nk-ghost {{
  /* Not quite transparent: a completely empty shell produces no image at all,
     and the layer-shell surface then stays stuck at GTK's fallback size. 1% is
     enough to force a render without showing anything. */
  background: alpha(@background, 0.01);
  border-color: transparent;
}}

.nk-pad {{ padding: 0 12px; }}
.nk-pad-lg {{ padding: 14px 16px; }}

/* --- compact state: the same metrics as waybar's pills --- */
.nk-root .nk-pill {{ padding: 0 {pad_x}px; }}
.nk-root .nk-pill label {{
  font-family: {bar_font};
  font-weight: {bar_weight};
  /* A percentage, not a pixel size: it resolves against GTK's default font,
     exactly the base waybar applies its own against. Recomputing it in pixels
     gave text a third too large. */
  font-size: {bar_size};
  color: @secondary;
}}
.nk-root .nk-pill .nk-compact-title {{ font-style: italic; }}
/* Player logos fill far more of their em than the bar's icons do: at equal
   font size they overshot by 3 px. */
.nk-root .nk-pill .nk-glyph {{ font-size: {glyph_size}; }}
.nk-thumb {{
  border-radius: 3px;
  background: alpha(@on_surface, 0.10);
}}
.nk-clock {{ font-size: 11.5px; font-weight: 600; letter-spacing: 0.4px; }}

/* --- panel typography --- */
.nk-title {{ font-size: 14px; font-weight: 700; }}
.nk-artist {{ font-size: 12px; color: @primary; }}
.nk-meta {{ font-size: 10.5px; color: @on_surface_variant; }}
.nk-sec {{
  font-size: 9.5px; letter-spacing: 1.4px; font-weight: 700;
  color: alpha(@on_surface_variant, 0.85);
}}
.nk-empty {{ font-size: 11.5px; color: @on_surface_variant; }}

/* --- cover art --- */
.nk-cover {{
  border-radius: 10px;
  background: @surface_container;
  border: 1px solid alpha(@outline, 0.18);
}}
.nk-cover-badge {{
  background: @surface_container_high;
  border-radius: 999px;
  padding: 3px;
}}

/* --- media controls --- */
.nk-root button.nk-ctl {{
  min-width: 26px; min-height: 26px; padding: 0;
  background: none; border: none; box-shadow: none;
  border-radius: 999px;
  color: @on_surface;
}}
.nk-root button.nk-ctl:hover {{ background: alpha(@primary, 0.16); }}
.nk-root button.nk-ctl:disabled {{ opacity: 0.3; }}
.nk-root button.nk-play {{
  min-width: 34px; min-height: 34px;
  background: alpha(@primary, 0.16);
  color: @primary;
}}
.nk-root button.nk-play:hover {{ background: alpha(@primary, 0.28); }}
.nk-root button.nk-ctl.nk-on {{ color: @primary; }}

/* --- progress bar: thin, clickable --- */
.nk-scale {{ min-height: 14px; }}
.nk-scale trough {{
  min-height: 4px; border-radius: 999px;
  background: alpha(@on_surface, 0.16);
}}
.nk-scale highlight {{ min-height: 4px; border-radius: 999px; background: @primary; }}
.nk-scale slider {{
  min-width: 10px; min-height: 10px; margin: 0;
  background: none; border: none; box-shadow: none;
}}
.nk-scale:hover slider {{ background: @primary; border-radius: 999px; }}

/* --- notes --- */
/* The theme puts an opaque background on a text view's `text` node: it made a
   light slab in the middle of the panel. */
.nk-root .nk-note, .nk-root .nk-note text {{
  background: transparent;
  font-size: 11px;
}}

/* --- right-column tabs --- */
.nk-root button.nk-tab {{
  min-width: 22px; min-height: 22px; padding: 0;
  background: none; border: none; box-shadow: none;
  border-radius: 7px; color: alpha(@on_surface_variant, 0.7);
}}
.nk-root button.nk-tab:hover {{ background: alpha(@on_surface, 0.08); }}
.nk-root button.nk-tab.nk-on {{ background: alpha(@primary, 0.18); color: @primary; }}

/* --- calendar --- */
.nk-month {{ font-size: 13px; font-weight: 700; }}
.nk-year {{ font-size: 11px; color: @on_surface_variant; }}
.nk-dow {{ font-size: 9px; color: alpha(@on_surface_variant, 0.75); font-weight: 700; }}
.nk-day {{ font-size: 10.5px; }}
.nk-day-out {{ font-size: 10.5px; color: alpha(@on_surface_variant, 0.35); }}
.nk-today {{
  font-size: 10.5px; font-weight: 700;
  color: @on_primary; background: @primary;
  border-radius: 999px;
}}
.nk-event-bar {{ background: @primary; border-radius: 999px; min-width: 2px; }}
.nk-event-name {{ font-size: 11px; font-weight: 600; }}
.nk-event-time {{ font-size: 10px; color: @on_surface_variant; }}

/* --- system --- */
.nk-stat-key {{ font-size: 10px; letter-spacing: 0.8px; color: @on_surface_variant; }}
.nk-stat-val {{ font-size: 11px; font-weight: 700; }}
.nk-gauge trough {{ min-height: 3px; border-radius: 999px; background: alpha(@on_surface, 0.14); }}
.nk-gauge progress {{ min-height: 3px; border-radius: 999px; background: @primary; }}

/* --- file shelf --- */
.nk-drop {{
  border: 1px dashed alpha(@outline, 0.45);
  border-radius: 12px;
  padding: 14px 10px;
}}
.nk-file {{
  padding: 4px 8px;
  border-radius: 8px;
  background: alpha(@on_surface, 0.06);
}}
.nk-file:hover {{ background: alpha(@primary, 0.16); }}
.nk-file-name {{ font-size: 11px; }}

.nk-sep {{ background: alpha(@outline, 0.18); min-width: 1px; min-height: 1px; }}

/* --- airdrop: the same visual grammar as HyprWhale --- */
/* The logo carries the state: grey at rest, it only takes on a colour to flag
   something out of the ordinary. It is the first thing read on arrival. */
.nk-root .nk-logo {{ color: alpha(@on_surface, 0.30); }}
.nk-root .nk-logo.nk-run  {{ color: @primary; }}
.nk-root .nk-logo.nk-busy {{ color: @tertiary; }}
.nk-root .nk-logo.nk-down {{ color: @error; }}
.nk-root .nk-name {{ font-weight: 700; font-size: 14px; letter-spacing: 0.3px; }}
.nk-root .nk-state {{ font-size: 11px; color: @on_surface_variant; }}

/* An outlined button rather than a solid slab. */
.nk-root button.nk-act {{
  min-height: 24px; padding: 0 10px; font-size: 11px;
  border-radius: 7px;
  background: none; box-shadow: none;
  border: 1px solid alpha(@primary, 0.55);
  color: @primary;
}}
.nk-root button.nk-act:hover {{ background: alpha(@primary, 0.16); }}
.nk-root button.nk-act:disabled {{
  border-color: alpha(@on_surface, 0.18);
  color: alpha(@on_surface_variant, 0.5);
}}

/* The recipient picker's bubbles: one circle per device, like the iOS share
   sheet. Round means height = width AND a radius past half of it, otherwise GTK
   renders a square with softened corners. */
.nk-root button.nk-bubble {{
  min-width: 46px; min-height: 46px; padding: 0;
  border-radius: 999px;
  background: alpha(@primary, 0.12);
  border: 1px solid alpha(@primary, 0.35);
  color: @primary;
  box-shadow: none;
}}
.nk-root button.nk-bubble:hover {{
  background: alpha(@primary, 0.24);
  border-color: @primary;
}}

/* A secondary action, sitting in a section heading: it must not carry the
   weight of a button. */
.nk-root button.nk-link {{
  min-height: 0; padding: 1px 6px;
  background: none; border: none; box-shadow: none;
  color: alpha(@on_surface_variant, 0.85);
  font-size: 10px; letter-spacing: 0.6px;
}}
.nk-root button.nk-link:hover {{ color: @primary; background: none; }}
.nk-root button.nk-link:disabled {{ opacity: 0.35; }}


.nk-root switch {{
  min-width: 38px; min-height: 20px;
  border: none; box-shadow: none;
  border-radius: 999px;
  background: alpha(@on_surface, 0.16);
}}
.nk-root switch:checked {{ background: @primary; }}
.nk-root switch:disabled {{ opacity: 0.35; }}
.nk-root switch slider {{
  min-width: 16px; min-height: 16px;
  border: none; box-shadow: none;
  border-radius: 999px;
  background: @surface;
}}
.nk-root switch:checked slider {{ background: @on_primary; }}
"""


def read_palette(path):
    colors = dict(FALLBACK)
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as fh:
            for name, value in DEFINE.findall(fh.read()):
                colors[name] = value.strip()
    except OSError:
        pass
    return colors


def gtk_font_px():
    """GTK's default font size, in pixels. waybar expresses its own as a
    percentage of this base; we redo the same calculation."""
    try:
        name = Gtk.Settings.get_default().props.gtk_font_name or ""
        points = float(name.rsplit(" ", 1)[-1])
        return points * 4.0 / 3.0
    except (AttributeError, ValueError, TypeError):
        return 14.666


def build_css(palette, radius, opacity, bar=None):
    bar = bar or waybar.read_bar()
    try:
        percent = float(bar["font_size"].rstrip("%")) / 100.0
    except (KeyError, ValueError):
        percent = 1.0
    # waybar puts its percentage on the universal selector, so it reapplies at
    # every level of its hierarchy: the rendered text is far smaller than the
    # declared percentage. Taking the percentage at face value gave a pill a
    # third too large. BAR_SCALE is the measured factor between the two
    # renderings, not a theoretical value.
    effective = percent * BAR_SCALE
    head = "".join(f"@define-color {k} {v};\n" for k, v in palette.items())
    body = STYLE.format(
        radius=bar.get("radius", radius), opacity=opacity,
        pad_y=bar.get("pad_y", 3), pad_x=bar.get("pad_x", 10),
        bar_font=bar.get("font_family", "monospace"),
        bar_weight=bar.get("font_weight", "700"),
        bar_size=f"{effective * 100:.4g}%",
        glyph_size=f"{effective * 100 * GLYPH_RATIO:.4g}%")
    return (head + body).encode()


class Theme:
    """Loads the palette, applies it, and reloads when it changes."""

    def __init__(self, config, on_change=None):
        self.path = os.path.expanduser(
            config.get("theme", "colors", default="~/.config/waybar/colors.css"))
        self.radius = config.get("appearance", "radius", default=18)
        self.opacity = config.get("appearance", "opacity", default=0.92)
        self.on_change = on_change
        self.bar = waybar.read_bar()
        self.palette = {}
        self.provider = Gtk.CssProvider()
        self.monitor = None
        self.apply()

        if config.get("theme", "follow_system", default=True):
            self._watch()

    def apply(self):
        self.bar = waybar.read_bar()
        self.palette = read_palette(self.path)
        self.provider.load_from_data(
            build_css(self.palette, self.radius, self.opacity, self.bar))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def reload(self, *_):
        self.apply()
        if self.on_change:
            self.on_change()

    def _watch(self):
        # The palette, plus the files HyprSettings rewrites: a slider moved in
        # the settings panel shows up in the notch too.
        self.monitor = []
        for path in [self.path, *waybar.watched_paths()]:
            try:
                gfile = Gio.File.new_for_path(path)
                monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
                monitor.connect("changed", self._on_file_event)
                self.monitor.append(monitor)
            except Exception:
                pass

    def _on_file_event(self, _m, _f, _o, event):
        # matugen rewrites the file: wait for the write to finish.
        if event in (Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                     Gio.FileMonitorEvent.CREATED,
                     Gio.FileMonitorEvent.RENAMED):
            self.reload()

    def color(self, name, default="#888888"):
        return self.palette.get(name, default)
