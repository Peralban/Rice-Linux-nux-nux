#!/bin/bash
# Capture une zone : enregistre le fichier ET le copie dans le presse-papier.

DIR="$HOME/Pictures/Screenshots"
mkdir -p "$DIR"
FILE="$DIR/$(date +%Y-%m-%d_%H-%M-%S).png"

# slurp renvoie un code non nul si tu annules avec Echap
GEO=$(slurp) || exit 0

grim -g "$GEO" "$FILE" || exit 1
wl-copy < "$FILE"

notify-send -i "$FILE" "Capture enregistrée" \
    "Copiée dans le presse-papier — $(basename "$FILE")"
