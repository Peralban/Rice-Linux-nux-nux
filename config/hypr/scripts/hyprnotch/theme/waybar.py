"""Lecture des réglages de la waybar, pour que le notch s'y aligne.

HyprSettings écrit la hauteur, les marges, la graisse, la taille de police
et le rembourrage des bulles. Plutôt que de dupliquer ces valeurs dans une
deuxième configuration, on relit les fichiers de la barre : changer un
curseur dans HyprSettings déplace aussi le notch.
"""

import json
import os
import re
import socket

CONFIG = os.path.expanduser("~/.config/waybar/config")
STYLE = os.path.expanduser("~/.config/waybar/style.css")

# La bulle : le bloc de règles partagé par tous les modules de la barre.
BUBBLE = re.compile(r"background-color: alpha\(@surface_container, 0\.75\);.*?\}", re.S)

DEFAULTS = {
    "font_family": '"JetBrainsMono Nerd Font Propo", "JetBrains Mono", monospace',
    "font_weight": "700",
    "font_size": "94%",
    "radius": 20,
    "pad_y": 3,
    "pad_x": 10,
    "margin_top": 1,
    "group_pad": 1,
}


def _paths():
    return os.path.realpath(CONFIG), os.path.realpath(STYLE)


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def read_bar():
    """Renvoie les métriques de la barre, valeurs par défaut à l'appui."""
    out = dict(DEFAULTS)
    config_path, style_path = _paths()

    config = _read(config_path)
    found = re.search(r'"margin-top"\s*:\s*(\d+)', config)
    if found:
        out["margin_top"] = int(found.group(1))

    style = _read(style_path)
    found = re.search(r"font-family:\s*([^;]+);", style)
    if found:
        out["font_family"] = found.group(1).strip()
    found = re.search(r"font-weight:\s*([A-Za-z0-9]+)\s*;", style)
    if found:
        out["font_weight"] = found.group(1).strip()
    found = re.search(r"font-size:\s*(\d+%)", style)
    if found:
        out["font_size"] = found.group(1)

    found = re.search(r"\.modules-center\s*\{[^}]*?padding-top:\s*(\d+)px", style, re.S)
    if found:
        out["group_pad"] = int(found.group(1))

    bubble = BUBBLE.search(style)
    if bubble:
        block = bubble.group(0)
        for key, pattern in (("radius", r"border-radius:\s*(\d+)px"),
                             ("pad_y", r"padding-top:\s*(\d+)px"),
                             ("pad_x", r"padding-left:\s*(\d+)px")):
            found = re.search(pattern, block)
            if found:
                out[key] = int(found.group(1))
    return out


def _hypr_socket():
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not signature:
        return None
    path = f"/run/user/{os.getuid()}/hypr/{signature}/.socket.sock"
    return path if os.path.exists(path) else None


def layer_geometry(namespace="waybar"):
    """Géométrie réelle de la barre, demandée au compositeur.

    Plus fiable que de recalculer une hauteur à partir de la police : c'est
    la mesure de ce qui est affiché, et elle suit toute seule les réglages
    changés dans HyprSettings."""
    path = _hypr_socket()
    if not path:
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            sock.connect(path)
            sock.sendall(b"j/layers")
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        data = json.loads(b"".join(chunks).decode())
    except (OSError, ValueError):
        return None
    for monitor in data.values():
        for group in monitor.get("levels", {}).values():
            for layer in group:
                if layer.get("namespace") == namespace:
                    return {"x": layer["x"], "y": layer["y"],
                            "w": layer["w"], "h": layer["h"]}
    return None


def island_metrics():
    """Hauteur et position verticale d'une bulle de la barre.

    La waybar entoure ses groupes de modules d'un rembourrage : la bulle
    occupe la hauteur de la barre moins ce rembourrage, en haut et en bas.
    """
    bar = read_bar()
    group_pad = bar.get("group_pad", 1)
    layer = layer_geometry()
    if not layer:
        return None
    return {"height": max(1, layer["h"] - 2 * group_pad),
            "top": layer["y"] + group_pad}


def watched_paths():
    """Les fichiers à surveiller pour suivre HyprSettings en direct."""
    return [path for path in _paths() if path]
