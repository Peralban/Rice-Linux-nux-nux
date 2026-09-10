#!/usr/bin/env bash
# Installe le theme SDDM "silent" configure comme l'ecran de verrouillage.
# Necessite sudo : le theme et la config de SDDM vivent hors du home.
set -euo pipefail

THEME=/usr/share/sddm/themes/silent
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WALL="$(readlink -f "$HOME/.config/hypr/current_wallpaper")"

[ -d "$THEME" ] || { echo "Theme absent. Installe-le : yay -S sddm-silent-theme" >&2; exit 1; }
[ -f "$WALL" ] || { echo "Aucun fond d'ecran courant. Choisis-en un avec Super+W." >&2; exit 1; }

# le service sddm tourne sous l'utilisateur sddm, qui ne peut pas lire /home :
# le fond doit donc etre copie dans un emplacement lisible par tous.
sudo install -Dm644 "$WALL" "$THEME/backgrounds/wallpaper.png"
sudo install -Dm644 "$HERE/hyprlock.conf" "$THEME/configs/hyprlock.conf"
sudo sed -i 's|^ConfigFile=.*|ConfigFile=configs/hyprlock.conf|' "$THEME/metadata.desktop"

sudo install -Dm644 /dev/stdin /etc/sddm.conf.d/theme.conf <<'CONF'
[Theme]
Current=silent
CONF

echo "Theme installe. Previsualise sans redemarrer :"
echo "  sddm-greeter-qt6 --test-mode --theme $THEME"
