#!/usr/bin/env bash
# Relie les fichiers du dépôt dans ~/.config, sans jamais copier.
#
# Sans argument, tout est installé. Avec des noms de composants, seuls
# ceux-là le sont : on peut donc prendre la barre sans le lanceur, ou le
# notch sans l'écran de connexion, sans avoir à trier les liens à la main
# après coup.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO/config"
DEST="${XDG_CONFIG_HOME:-$HOME/.config}"
BACKUP="$HOME/.config-backup-$(date +%Y%m%d-%H%M%S)"

# nom | chemins dans config/ | ce que c'est
# Un composant sans chemin n'est pas lié : il ne contient que de la
# documentation et des correctifs à appliquer ailleurs.
COMPONENTS=(
  "hypr|hypr|Hyprland, le notch et les scripts du bureau"
  "waybar|waybar|la barre"
  "matugen|matugen|la palette Material You générée depuis le fond d'écran"
  "swaync|swaync|le centre de notifications"
  "vicinae|vicinae|le lanceur"
  "gtk|gtk-3.0 gtk-4.0|les thèmes GTK 3 et 4"
  "airdrop||AirDrop : correctifs et outils, voir config/airdrop/README.md"
)

# Ce qui casse visiblement sans son voisin. Ce ne sont pas des dépendances
# dures - rien ne plante - mais l'un sans l'autre donne un résultat qui
# ressemble à une installation ratée, donc on le dit.
declare -A SUGGESTS=(
  [waybar]="matugen"
  [hypr]="matugen waybar"
  [swaync]="matugen"
)

usage() {
  cat <<EOF
Usage: ./install.sh [composant...]

Sans argument : tout est installé.

Composants :
EOF
  local entry name paths desc
  for entry in "${COMPONENTS[@]}"; do
    IFS='|' read -r name paths desc <<<"$entry"
    printf '  %-9s %s\n' "$name" "$desc"
  done
  cat <<EOF

  --list    n'affiche que cette liste
  --dry-run montre ce qui serait lié, sans rien toucher

L'écran de connexion SDDM est à part, il demande root :
  system/sddm/install-sddm.sh
EOF
}

paths_of() {
  local entry name paths desc
  for entry in "${COMPONENTS[@]}"; do
    IFS='|' read -r name paths desc <<<"$entry"
    [ "$name" = "$1" ] && { printf '%s' "$paths"; return 0; }
  done
  return 1
}

known() { paths_of "$1" >/dev/null 2>&1; }

DRY=0
WANTED=()
for arg in "$@"; do
  case "$arg" in
    -h|--help|--list) usage; exit 0 ;;
    --dry-run) DRY=1 ;;
    -*) echo "option inconnue : $arg" >&2; usage >&2; exit 2 ;;
    *)
      known "$arg" || { echo "composant inconnu : $arg" >&2; usage >&2; exit 2; }
      WANTED+=("$arg") ;;
  esac
done

if [ ${#WANTED[@]} -eq 0 ]; then
  for entry in "${COMPONENTS[@]}"; do WANTED+=("${entry%%|*}"); done
fi

[ -d "$SRC" ] || { echo "Dossier config/ introuvable dans $REPO" >&2; exit 1; }

linked=0 saved=0 skipped=0

# `find` parcourt le disque, pas l'index git : sans les exclusions plus bas
# on lie les artefacts que .gitignore écarte pourtant, et ~/.config se
# retrouve avec des __pycache__ pointant vers le dépôt.
link_tree() {
  local sub="$1" root="$SRC/$sub"
  [ -d "$root" ] || return 0
  while IFS= read -r -d '' file; do
    local rel="${file#"$SRC"/}" target
    target="$DEST/$rel"

    # déjà le bon lien : rien à faire
    if [ -L "$target" ] && [ "$(readlink -f "$target")" = "$(readlink -f "$file")" ]; then
      skipped=$((skipped + 1)); continue
    fi

    if [ "$DRY" = 1 ]; then
      echo "  lierait $rel"; linked=$((linked + 1)); continue
    fi

    mkdir -p "$(dirname "$target")"

    # on met de côté ce qu'on remplace, sans jamais l'écraser
    if [ -e "$target" ] || [ -L "$target" ]; then
      mkdir -p "$BACKUP/$(dirname "$rel")"
      mv "$target" "$BACKUP/$rel"
      saved=$((saved + 1))
    fi

    ln -s "$file" "$target"
    linked=$((linked + 1))
  done < <(find "$root" \
             \( -name __pycache__ -o -name '*.egg-info' \) -prune -o \
             -type f ! -name '*.pyc' ! -name '*.bak' ! -name '*.bak[0-9]' \
             -print0)
}

for name in "${WANTED[@]}"; do
  paths="$(paths_of "$name")"
  if [ -z "$paths" ]; then
    [ ${#WANTED[@]} -eq 1 ] && echo "$name : rien à lier, voir config/$name/README.md"
    continue
  fi
  for sub in $paths; do link_tree "$sub"; done

  # On ne suggère que ce qui n'a pas été demandé dans le même appel.
  for dep in ${SUGGESTS[$name]:-}; do
    case " ${WANTED[*]} " in
      *" $dep "*) ;;
      *) echo "note : $name se présente mal sans $dep" ;;
    esac
  done
done

if [ "$DRY" = 1 ]; then
  echo "$linked lien(s) seraient créés, $skipped déjà en place"
  exit 0
fi

echo "$linked lien(s) créé(s), $skipped déjà en place"
[ "$saved" -gt 0 ] && echo "$saved fichier(s) existant(s) déplacé(s) vers $BACKUP"

cat <<'EOF'

Reste à faire à la main :
  hyprctl reload                       recharger Hyprland
  ~/.config/hypr/scripts/wbrestart.sh  redémarrer waybar
  matugen image <une-image>            générer la palette et la propager

Les dépendances sont listées dans le README.
EOF
