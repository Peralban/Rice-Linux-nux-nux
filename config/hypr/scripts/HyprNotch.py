#!/usr/bin/env python3
"""HyprNotch -- a dynamic notch for Hyprland (bilingual FR / EN).

Media (MPRIS), calendar, system and notifications in a layer-shell surface
anchored at the top of the screen, opening on hover.

Like HyprWhale, it has no palette of its own: it reads the one matugen
regenerates on every wallpaper change.
"""

import os
import sys

# gtk4-layer-shell has to be loaded before libwayland-client. Python loads
# libwayland first through gi, so we re-exec ourselves once with LD_PRELOAD.
_LIB = "/usr/lib/libgtk4-layer-shell.so"
if os.path.exists(_LIB) and "libgtk4-layer-shell" not in os.environ.get("LD_PRELOAD", ""):
    existing = os.environ.get("LD_PRELOAD", "")
    os.environ["LD_PRELOAD"] = f"{_LIB}:{existing}" if existing else _LIB
    os.execv(sys.executable, [sys.executable, os.path.abspath(__file__), *sys.argv[1:]])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hyprnotch.app import main  # noqa: E402

if __name__ == "__main__":
    main()
