#!/usr/bin/env bash
# Relie chaque fichier du dépôt dans ~/.config, sans jamais copier.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO/config"
DEST="${XDG_CONFIG_HOME:-$HOME/.config}"
BACKUP="$HOME/.config-backup-$(date +%Y%m%d-%H%M%S)"

[ -d "$SRC" ] || { echo "Dossier config/ introuvable dans $REPO" >&2; exit 1; }

linked=0 saved=0

while IFS= read -r -d '' file; do
    rel="${file#"$SRC"/}"
    target="$DEST/$rel"

    # deja le bon lien : rien a faire
    if [ -L "$target" ] && [ "$(readlink -f "$target")" = "$(readlink -f "$file")" ]; then
        continue
    fi

    mkdir -p "$(dirname "$target")"

    # on met de cote ce qu'on remplace, sans jamais l'ecraser
    if [ -e "$target" ] || [ -L "$target" ]; then
        mkdir -p "$BACKUP/$(dirname "$rel")"
        mv "$target" "$BACKUP/$rel"
        saved=$((saved + 1))
    fi

    ln -s "$file" "$target"
    linked=$((linked + 1))
done < <(find "$SRC" -type f -print0)

echo "$linked lien(s) créé(s)"
[ "$saved" -gt 0 ] && echo "$saved fichier(s) existant(s) déplacé(s) vers $BACKUP"

cat <<'EOF'

Reste à faire à la main :
  hyprctl reload                       recharger Hyprland
  ~/.config/hypr/scripts/wbrestart.sh  redémarrer waybar
  matugen image <une-image>            générer la palette et la propager

Les dépendances sont listées dans le README.
EOF
