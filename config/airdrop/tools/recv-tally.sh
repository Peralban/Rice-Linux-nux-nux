#!/usr/bin/env bash
# Compte les receptions par ISSUE, pas seulement par nombre.
#
# Trois issues distinctes, qui n'ont pas la meme signification :
#   direct   le transfert est alle au bout tout seul
#   sauve    il a cale, le delai d'expiration a coupe, et les blocs recus
#            contenaient quand meme le fichier complet
#   partiel  il a cale trop tot ; le fichier est incomplet et suffixe
#            .partial plutot que livre comme bon
L=/run/user/1000/airdropd/airdropd.log
[ -r "$L" ] || { echo "pas de journal : le demon tourne-t-il ?"; exit 1; }
start=$(grep -c 'Receiving file'   "$L"); start=${start:-0}
extr=$(grep -c 'Extracted into'    "$L"); extr=${extr:-0}
salv=$(grep -c 'salvaging what'    "$L"); salv=${salv:-0}
part=$(grep -c 'kept as .partial'  "$L"); part=${part:-0}
direct=$((extr - salv > 0 ? extr - salv : 0))
printf 'demarres %s | direct %s | sauves %s | partiels %s | perdus %s\n' \
  "$start" "$direct" "$salv" "$part" "$((start - extr - part))"
