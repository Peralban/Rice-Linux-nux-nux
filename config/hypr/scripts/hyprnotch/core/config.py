"""The notch's configuration.

The file lives outside the repository (~/.config/hypr/scripts/.hyprnotch.json):
it is a per-machine setting, not a versioned customisation. Everything is
optional, and missing values fall back on DEFAULTS.
"""

import json
import os

PATH = os.path.expanduser("~/.config/hypr/scripts/.hyprnotch.json")
LANG_FILE = os.path.expanduser("~/.config/hypr/scripts/.hyprsettings-lang")

DEFAULTS = {
    "notch": {
        "monitor": "primary",       # "primary" | nom du connecteur, ex. "eDP-1"
        "layer": "top",             # "top" | "overlay"
        "margin_top": 0,            # décalage en plus de celui de la waybar
        "in_bar": True,             # ignorer la zone exclusive : le notch se pose DANS la barre
        "hover_to_open": True,
        "default_page": "calendar",   # calendar | system | files | airdrop | notes
        "close_delay_ms": 180,      # anti-clignotement quand la souris sort
    },
    "appearance": {
        "radius": 18,
        "opacity": 0.82,
        "animation_ms": 260,
        "compact": [230, 22],
        "expanded": [660, 224],
    },
    "widgets": {
        "media": True,
        "calendar": True,
        "system": True,
        "files": True,
        "airdrop": True,
        "notes": True,
    },
    "theme": {
        # The Material You palette matugen produces. One source of truth for
        # the whole desktop: we read waybar's file.
        "colors": "~/.config/waybar/colors.css",
        "follow_system": True,
    },
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(PATH, encoding="utf-8") as fh:
                self.data = _merge(DEFAULTS, json.load(fh))
        except (OSError, ValueError):
            self.data = dict(DEFAULTS)

    def get(self, *path, default=None):
        node = self.data
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def write_default(self):
        """Writes a commented file the first time round, so the user can see
        what there is to change."""
        if os.path.exists(PATH):
            return
        try:
            os.makedirs(os.path.dirname(PATH), exist_ok=True)
            with open(PATH, "w", encoding="utf-8") as fh:
                json.dump(DEFAULTS, fh, indent=2)
                fh.write("\n")
        except OSError:
            pass


def lang():
    """The same language file as HyprSettings / HyprWhale."""
    try:
        with open(LANG_FILE, encoding="utf-8") as fh:
            value = fh.read().strip()
            if value in ("fr", "en"):
                return value
    except OSError:
        pass
    return "fr"
