#!/usr/bin/env bash
# Counts receptions by OUTCOME, not merely by count.
#
# Three distinct outcomes, which do not mean the same thing:
#   direct    the transfer ran to completion on its own
#   salvaged  it stalled, the read timeout cut it off, and the blocks received
#             still contained the complete file
#   partial   it stalled too early; the file is incomplete and suffixed
#             .partial rather than delivered as good
L=/run/user/1000/airdropd/airdropd.log
[ -r "$L" ] || { echo "pas de journal : le demon tourne-t-il ?"; exit 1; }
start=$(grep -c 'Receiving file'   "$L"); start=${start:-0}
extr=$(grep -c 'Extracted into'    "$L"); extr=${extr:-0}
salv=$(grep -c 'salvaging what'    "$L"); salv=${salv:-0}
part=$(grep -c 'kept as .partial'  "$L"); part=${part:-0}
direct=$((extr - salv > 0 ? extr - salv : 0))
printf 'demarres %s | direct %s | sauves %s | partiels %s | perdus %s\n' \
  "$start" "$direct" "$salv" "$part" "$((start - extr - part))"
