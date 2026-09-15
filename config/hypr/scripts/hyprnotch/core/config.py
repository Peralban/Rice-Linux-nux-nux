"""Configuration du notch.

Le fichier vit hors du dépôt (~/.config/hypr/scripts/.hyprnotch.json) : c'est
un réglage machine, pas une personnalisation versionnée. Tout est optionnel,
les valeurs manquantes retombent sur DEFAULTS.
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
        # Palette Material You produite par matugen. Une seule source de
        # vérité pour tout le bureau : on lit le fichier de la waybar.
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
        """Écrit un fichier commenté la première fois, pour que l'utilisateur
        voie ce qu'il peut changer."""
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
    """Même fichier de langue que HyprSettings / HyprWhale."""
    try:
        with open(LANG_FILE, encoding="utf-8") as fh:
            value = fh.read().strip()
            if value in ("fr", "en"):
                return value
    except OSError:
        pass
    return "fr"
