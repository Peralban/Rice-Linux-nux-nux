#!/bin/bash
# Captures a region: saves the file AND copies it to the clipboard.

DIR="$HOME/Pictures/Screenshots"
mkdir -p "$DIR"
FILE="$DIR/$(date +%Y-%m-%d_%H-%M-%S).png"

# slurp returns a non-zero status if you cancel with Escape
GEO=$(slurp) || exit 0

grim -g "$GEO" "$FILE" || exit 1
wl-copy < "$FILE"

notify-send -i "$FILE" "Capture enregistrée" \
    "Copiée dans le presse-papier — $(basename "$FILE")"
