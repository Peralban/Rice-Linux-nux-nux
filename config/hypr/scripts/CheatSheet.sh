#!/bin/bash
# Affiche tous les raccourcis definis dans keybinds.conf via rofi.
# Se met a jour tout seul : les fichiers sont relus a chaque ouverture.

CONF="$HOME/.config/hypr/configs/keybinds.conf"
MAIN="$HOME/.config/hypr/hyprland.conf"
ROFI_CONF="$HOME/.config/rofi/config.rasi"

val() { grep -m1 "^\\\$$1" "$2" | sed 's/^[^=]*=//; s/#.*//' | xargs; }

MOD=$(val mainMod "$CONF")
TERM=$(val terminal "$MAIN")
FILES=$(val fileManager "$MAIN")
MENU=$(val menu "$MAIN")

grep -E '^bind[a-z]* *=' "$CONF" | while IFS= read -r line; do
    body=${line#*=}
    mods=$(printf '%s' "$body" | cut -d, -f1 | xargs)
    key=$(printf '%s'  "$body" | cut -d, -f2 | xargs)
    action=$(printf '%s' "$body" | cut -d, -f3- | sed 's/#.*//' | xargs)

    mods=${mods//\$mainMod/$MOD}
    [ -n "$mods" ] && combo="$mods $key" || combo="$key"
    combo=$(printf '%s' "$combo" | xargs | sed 's/ / + /g')

    action=${action#exec,}
    action=${action%,}
    action=${action//\$terminal/$TERM}
    action=${action//\$fileManager/$FILES}
    action=${action//\$menu/$MENU}
    action=${action//\~\/.config\/hypr\/scripts\//}
    action=$(printf '%s' "$action" | xargs)

    printf '%-30s   %s\n' "$combo" "$action"
done | rofi -dmenu -i -config "$ROFI_CONF" -p "" \
    -mesg "   Raccourcis Hyprland — tape pour filtrer" \
    -theme-str 'window {width: 62%;} listview {lines: 16;} element-text {font: "JetBrains Mono 10";}'
