#!/usr/bin/env python3
"""HyprNotch — un notch dynamique pour Hyprland (bilingue FR / EN).

Média (MPRIS), calendrier, système et notifications dans une surface
layer-shell ancrée en haut de l'écran, qui s'ouvre au survol.

Comme HyprWhale, il n'a pas de palette propre : il lit celle que matugen
régénère à chaque changement de fond d'écran.
"""

import os
import sys

# gtk4-layer-shell doit être chargé avant libwayland-client. Python charge
# libwayland en premier via gi, donc on se relance une fois avec LD_PRELOAD.
_LIB = "/usr/lib/libgtk4-layer-shell.so"
if os.path.exists(_LIB) and "libgtk4-layer-shell" not in os.environ.get("LD_PRELOAD", ""):
    existing = os.environ.get("LD_PRELOAD", "")
    os.environ["LD_PRELOAD"] = f"{_LIB}:{existing}" if existing else _LIB
    os.execv(sys.executable, [sys.executable, os.path.abspath(__file__), *sys.argv[1:]])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hyprnotch.app import main  # noqa: E402

if __name__ == "__main__":
    main()
