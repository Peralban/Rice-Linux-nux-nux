#!/bin/sh
# Refresh GTK3 applications after matugen regenerated the palette.
#
# GTK3 reads ~/.config/gtk-3.0/gtk.css once per process and never looks at it
# again. Measured here, all three of the usual tricks fail on a running
# application: rewriting the imported palette, touching gtk.css, and toggling
# gtk-theme through gsettings. Starting the process afresh is the only thing
# that picks up a new colour.
#
# Thunar compounds it by reusing its running instance over D-Bus, so a single
# stale process would serve the old palette to every window it opens from then
# on. Quitting it is therefore not optional - but only while nothing is open,
# because changing a wallpaper must never close a directory you were browsing.
# Windows left open keep the previous palette until you close them.

command -v thunar >/dev/null 2>&1 || exit 0

open=0
if command -v hyprctl >/dev/null 2>&1; then
    open=$(hyprctl clients -j 2>/dev/null | grep -ci '"class": *"thunar"')
fi

[ "$open" -eq 0 ] && thunar -q >/dev/null 2>&1

exit 0
