"""Pont entre matugen et le notch.

Aucune couleur n'est écrite en dur. On relit le fichier que matugen génère
déjà pour la waybar — il contient la palette Material You complète — et on
le concatène devant notre feuille de style. Quand le fond d'écran change,
matugen réécrit le fichier, le moniteur le voit et le thème suit.
"""

import os
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, Gtk  # noqa: E402

from . import waybar  # noqa: E402

DEFINE = re.compile(r"@define-color\s+([a-z0-9_]+)\s+([^;]+);")

# Ramène les logos de lecteur à la hauteur des icônes de la waybar.
GLYPH_RATIO = 0.95

# Écart mesuré entre la taille annoncée par la waybar et celle qu'elle
# dessine réellement : hauteur de capitale comparée au pixel sur la barre.
BAR_SCALE = 0.782

# Repli minimal si matugen n'a jamais tourné : gris neutres, jamais une
# couleur d'accent inventée.
FALLBACK = {
    "background": "#141414", "surface": "#141414",
    "surface_container": "#1e1e1e", "surface_container_high": "#282828",
    "on_surface": "#e6e6e6", "on_surface_variant": "#b4b4b4",
    "outline": "#8a8a8a", "outline_variant": "#3a3a3a",
    "primary": "#d0bcff", "on_primary": "#20124a",
    "secondary": "#ccc2dc", "tertiary": "#efb8c8",
}

STYLE = """
window, window.background {{ background: transparent; }}
/* Le thème pose un fond opaque sur scrolledwindow et viewport ; il se
   voyait au travers de la coque au repos. */
scrolledwindow, viewport, stack {{ background: transparent; }}

.nk-root, .nk-root label, .nk-root button {{
  font-family: "JetBrainsMono Nerd Font Propo", "JetBrains Mono", monospace;
  color: @on_surface;
}}

/* La coque. Le seul élément qui dessine un fond : tout le reste est posé
   dessus, ce qui garde les coins arrondis propres pendant l'animation. */
.nk-shell {{
  background: alpha(@background, {opacity});
  border: 1px solid alpha(@outline, 0.22);
  border-radius: {radius}px;
  /* La coque s'efface en fondu plutôt que d'un coup quand la pastille
     redevient invisible. */
  transition: background-color 140ms ease-out, border-color 140ms ease-out;
}}

/* Au repos, sans lecture en cours : la coque ne dessine plus rien, mais la
   surface reste là — on peut toujours la survoler pour ouvrir le panneau. */
.nk-shell.nk-ghost {{
  /* Pas tout à fait transparent : une coque totalement vide ne produit
     aucune image, et la surface layer-shell reste alors figée à la taille
     de repli de GTK. 1 % suffit à forcer le rendu sans rien montrer. */
  background: alpha(@background, 0.01);
  border-color: transparent;
}}

.nk-pad {{ padding: 0 12px; }}
.nk-pad-lg {{ padding: 14px 16px; }}

/* --- état compact : mêmes mesures que les bulles de la waybar --- */
.nk-root .nk-pill {{ padding: 0 {pad_x}px; }}
.nk-root .nk-pill label {{
  font-family: {bar_font};
  font-weight: {bar_weight};
  /* Le pourcentage, pas une taille en pixels : il se résout sur la police
     GTK par défaut, exactement la base sur laquelle la waybar applique le
     sien. Recalculer en pixels donnait un texte un tiers trop grand. */
  font-size: {bar_size};
  color: @secondary;
}}
.nk-root .nk-pill .nk-compact-title {{ font-style: italic; }}
/* Les logos de lecteur remplissent bien plus leur cadratin que les icônes
   de la barre : à taille de police égale ils sortaient de 3 px. */
.nk-root .nk-pill .nk-glyph {{ font-size: {glyph_size}; }}
.nk-thumb {{
  border-radius: 3px;
  background: alpha(@on_surface, 0.10);
}}
.nk-clock {{ font-size: 11.5px; font-weight: 600; letter-spacing: 0.4px; }}

/* --- typographie du panneau --- */
.nk-title {{ font-size: 14px; font-weight: 700; }}
.nk-artist {{ font-size: 12px; color: @primary; }}
.nk-meta {{ font-size: 10.5px; color: @on_surface_variant; }}
.nk-sec {{
  font-size: 9.5px; letter-spacing: 1.4px; font-weight: 700;
  color: alpha(@on_surface_variant, 0.85);
}}
.nk-empty {{ font-size: 11.5px; color: @on_surface_variant; }}

/* --- pochette --- */
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

/* --- contrôles média --- */
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

/* --- barre de progression : fine, cliquable --- */
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

/* --- onglets de la colonne droite --- */
.nk-root button.nk-tab {{
  min-width: 22px; min-height: 22px; padding: 0;
  background: none; border: none; box-shadow: none;
  border-radius: 7px; color: alpha(@on_surface_variant, 0.7);
}}
.nk-root button.nk-tab:hover {{ background: alpha(@on_surface, 0.08); }}
.nk-root button.nk-tab.nk-on {{ background: alpha(@primary, 0.18); color: @primary; }}

/* --- calendrier --- */
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

/* --- système --- */
.nk-stat-key {{ font-size: 10px; letter-spacing: 0.8px; color: @on_surface_variant; }}
.nk-stat-val {{ font-size: 11px; font-weight: 700; }}
.nk-gauge trough {{ min-height: 3px; border-radius: 999px; background: alpha(@on_surface, 0.14); }}
.nk-gauge progress {{ min-height: 3px; border-radius: 999px; background: @primary; }}

/* --- étagère à fichiers --- */
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

/* --- airdrop --- */
.nk-root button.nk-btn {{
  min-height: 26px; padding: 3px 12px;
  border: none; box-shadow: none;
  border-radius: 999px;
  background: alpha(@primary, 0.16);
  color: @primary;
  font-size: 11px; font-weight: 600;
}}
.nk-root button.nk-btn:hover {{ background: alpha(@primary, 0.28); }}
.nk-root button.nk-btn:disabled {{ background: alpha(@on_surface, 0.06);
  color: alpha(@on_surface_variant, 0.5); }}

.nk-root switch {{
  min-width: 40px; min-height: 22px;
  border: none; box-shadow: none;
  border-radius: 999px;
  background: alpha(@on_surface, 0.16);
}}
.nk-root switch:checked {{ background: @primary; }}
.nk-root switch:disabled {{ opacity: 0.35; }}
.nk-root switch slider {{
  min-width: 18px; min-height: 18px;
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
    """Taille de police par défaut de GTK, en pixels. La waybar exprime la
    sienne en pourcentage de cette base ; on refait le même calcul."""
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
    # La waybar pose son pourcentage sur le sélecteur universel, donc il se
    # réapplique à chaque niveau de sa hiérarchie : le texte rendu est bien
    # plus petit que le pourcentage annoncé. Reprendre le pourcentage tel
    # quel donnait une pastille d'un tiers trop grande. BAR_SCALE est le
    # facteur mesuré entre les deux rendus, pas une valeur théorique.
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
    """Charge la palette, l'applique, et se recharge quand elle change."""

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
        # La palette, plus les fichiers que HyprSettings réécrit : un curseur
        # bougé dans le panneau de réglages se voit aussi dans le notch.
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
        # matugen réécrit le fichier : on attend la fin de l'écriture.
        if event in (Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                     Gio.FileMonitorEvent.CREATED,
                     Gio.FileMonitorEvent.RENAMED):
            self.reload()

    def color(self, name, default="#888888"):
        return self.palette.get(name, default)
