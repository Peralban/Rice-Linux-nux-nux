#!/usr/bin/env bash
# Links the repository's files into ~/.config, never copying.
#
# With no argument, everything is installed. With component names, only those
# are: so you can take the bar without the launcher, or the notch without the
# login screen, without having to sort the links out by hand afterwards.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO/config"
DEST="${XDG_CONFIG_HOME:-$HOME/.config}"
BACKUP="$HOME/.config-backup-$(date +%Y%m%d-%H%M%S)"

# name | paths under config/ | what it is
# A component with no path is not linked: it holds only documentation and
# patches to be applied elsewhere.
COMPONENTS=(
  "hypr|hypr|Hyprland, le notch et les scripts du bureau"
  "waybar|waybar|la barre"
  "matugen|matugen|la palette Material You générée depuis le fond d'écran"
  "swaync|swaync|le centre de notifications"
  "vicinae|vicinae|le lanceur"
  "gtk|gtk-3.0 gtk-4.0|les thèmes GTK 3 et 4"
  "airdrop||AirDrop : correctifs et outils, voir config/airdrop/README.md"
)

# What visibly breaks without its neighbour. These are not hard dependencies -
# nothing crashes - but one without the other gives a result that looks like a
# failed install, so it is worth saying.
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

  --list    print this list only
  --dry-run show what would be linked, touching nothing

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

# `find` walks the disk, not the git index: without the exclusions below we
# link the artefacts .gitignore does exclude, and ~/.config ends up with
# __pycache__ directories pointing into the repository.
link_tree() {
  local sub="$1" root="$SRC/$sub"
  [ -d "$root" ] || return 0
  while IFS= read -r -d '' file; do
    local rel="${file#"$SRC"/}" target
    target="$DEST/$rel"

    # already the right link: nothing to do
    if [ -L "$target" ] && [ "$(readlink -f "$target")" = "$(readlink -f "$file")" ]; then
      skipped=$((skipped + 1)); continue
    fi

    if [ "$DRY" = 1 ]; then
      echo "  lierait $rel"; linked=$((linked + 1)); continue
    fi

    mkdir -p "$(dirname "$target")"

    # set aside whatever is being replaced, never overwrite it
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

  # Only suggest what was not asked for in the same invocation.
  for dep in ${SUGGESTS[$name]:-}; do
    case " ${WANTED[*]} " in
      *" $dep "*) ;;
      *) echo "note: $name looks wrong without $dep" ;;
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
