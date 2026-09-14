#!/usr/bin/env bash
# Enregistre l'etat du lien et de la resolution DNS, pour que le prochain gel
# laisse des traces au lieu d'etre reconstitue de memoire.
#
# Le gel observe se presente comme une perte de connexion, mais `nmcli` affiche
# la station associee et le navigateur rend ERR_NAME_NOT_RESOLVED : c'est donc
# la resolution qui tombe, pas la radio. Ce script mesure les deux separement,
# plus ce qui pourrait les relier - le fichier resolv.conf, la route par
# defaut, et la presence de la pile AirDrop sur la meme radio.
#
# Une ligne toutes les 10 s, en TSV. Volontairement leger : deux commandes
# reseau par tour, aucune qui puisse bloquer plus de 2 s.
set -u

LOG="${1:-$HOME/.cache/linkwatch.log}"
INTERVAL="${LINKWATCH_INTERVAL:-10}"
IFACE="${LINKWATCH_IFACE:-wlan0}"
MAXLINES=20000     # ~55 h ; au-dela on repart, le disque n'est pas le sujet

mkdir -p "$(dirname "$LOG")"
[ -s "$LOG" ] || printf 'heure\tassoc\tsignal\ttx\tgw_ms\tdns\tns\tresolv_mtime\troute\tairdrop\tvifs\tpair\tawdl_ms\n' > "$LOG"

gw() { ip route show default 2>/dev/null | awk '/default/{print $3; exit}'; }

# L'adresse lien-local du pair, deduite de la derniere adresse MAC qu'owl a
# rapportee. Mesurer la station ne suffit pas : on a observe une station
# parfaite - -45 dBm, 351 Mbit/s, box a 4 ms - pendant qu'AWDL perdait 100 %
# des paquets vers le telephone. Les deux couches partagent la radio mais
# tombent independamment, et c'est la seconde qui porte AirDrop.
peer6() {
  local mac
  # owl ecrit "widened 86:82:…:1b's sequence" - l'apostrophe est collee a
  # l'adresse, un motif qui attend une espace derriere ne matche jamais.
  mac=$(tail -c 200000 "${AIRDROP_OWL_LOG:-/run/airdrop-owl.log}" 2>/dev/null \
        | grep -aoE 'widened ([0-9a-f]{2}:){5}[0-9a-f]{2}' | tail -1 | awk '{print $2}')
  [ -n "$mac" ] || return 1
  printf '%s' "$mac" | awk -F: '{
    # EUI-64 : bit U/L inverse, fffe insere au milieu
    printf "fe80::%02x%s:%sff:fe%s:%s%s", xor(strtonum("0x" $1), 2), $2, $3, $4, $5, $6
  }' 2>/dev/null
}

while :; do
  now=$(date +%H:%M:%S)

  link=$(iw dev "$IFACE" link 2>/dev/null)
  if printf '%s' "$link" | grep -q "^Connected"; then
    assoc=oui
    signal=$(printf '%s' "$link" | awk '/signal:/{print $2}')
    tx=$(printf '%s' "$link" | awk '/tx bitrate:/{print $3}')
  else
    assoc=NON; signal=-; tx=-
  fi

  g=$(gw)
  if [ -n "$g" ]; then
    gw_ms=$(timeout 2 ping -c1 -W1 -n "$g" 2>/dev/null | awk -F'time=' '/time=/{print $2+0; exit}')
    gw_ms="${gw_ms:-PERTE}"
  else
    gw_ms=SANS_ROUTE
  fi

  # La resolution, mesuree separement du lien : c'est toute la question.
  if timeout 3 getent hosts github.com >/dev/null 2>&1; then dns=ok; else dns=ECHEC; fi

  ns=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf 2>/dev/null)
  rmt=$(date -r /etc/resolv.conf +%H:%M:%S 2>/dev/null)
  route="${g:--}"

  ad=$(sed -n 's/.*"state":"\([a-z]*\)".*/\1/p' \
        "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/airdropd/state.json" 2>/dev/null)
  vifs=$(ls /sys/class/net 2>/dev/null | grep -cE '^(go0|mon0|mon1|awdl0)$')

  # Le chemin qui porte reellement AirDrop, mesure a part.
  p6=$(peer6)
  if [ -n "${p6:-}" ] && ip link show awdl0 >/dev/null 2>&1; then
    awdl_ms=$(timeout 3 ping -6 -c2 -W1 -i 0.3 "$p6%awdl0" 2>/dev/null \
              | awk -F'time=' '/time=/{print $2+0; exit}')
    awdl_ms="${awdl_ms:-PERTE}"
    pair=vu
  else
    pair=-; awdl_ms=-
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$now" "$assoc" "${signal:--}" "${tx:--}" "$gw_ms" "$dns" \
    "${ns:--}" "${rmt:--}" "$route" "${ad:--}" "$vifs" "$pair" "$awdl_ms" >> "$LOG"

  if [ "$(wc -l < "$LOG")" -gt "$MAXLINES" ]; then
    tail -n $((MAXLINES / 2)) "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
  sleep "$INTERVAL"
done
