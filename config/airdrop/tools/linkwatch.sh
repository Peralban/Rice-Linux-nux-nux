#!/usr/bin/env bash
# Records the state of the link and of DNS resolution, so the next freeze
# leaves traces instead of being reconstructed from memory.
#
# The freeze presents as a lost connection, but `nmcli` shows the station
# associated and the browser returns ERR_NAME_NOT_RESOLVED: so it is resolution
# that falls over, not the radio. This script measures the two separately, plus
# what might tie them together - resolv.conf, the default route, and whether the
# AirDrop stack is on the same radio.
#
# One line every 10 s, in TSV. Deliberately light: two network commands per
# round, none that can block for more than 2 s.
set -u

LOG="${1:-$HOME/.cache/linkwatch.log}"
INTERVAL="${LINKWATCH_INTERVAL:-10}"
IFACE="${LINKWATCH_IFACE:-wlan0}"
MAXLINES=20000     # ~55 h ; au-dela on repart, le disque n'est pas le sujet

mkdir -p "$(dirname "$LOG")"
[ -s "$LOG" ] || printf 'quand\tassoc\tsignal\ttx\tgw_ms\tdns\tns\tresolv_mtime\troute\tairdrop\tvifs\tperte\tawdl_ms\n' > "$LOG"

gw() { ip route show default 2>/dev/null | awk '/default/{print $3; exit}'; }

# The peer's link-local address, derived from the last MAC address owl
# reported. Measuring the station is not enough: a perfect station was observed
# - -45 dBm, 351 Mbit/s, gateway at 4 ms - while AWDL was losing 100% of its
# packets to the phone. The two layers share the radio but fail independently,
# and it is the second one that carries AirDrop.
peer6() {
  local mac
  # owl writes "widened 86:82:...:1b's sequence" - the apostrophe is stuck to
  # the address, so a pattern expecting a space after it never matches.
  mac=$(tail -c 200000 "${AIRDROP_OWL_LOG:-/run/airdrop-owl.log}" 2>/dev/null \
        | grep -aoE 'widened ([0-9a-f]{2}:){5}[0-9a-f]{2}' | tail -1 | awk '{print $2}')
  [ -n "$mac" ] || return 1
  printf '%s' "$mac" | awk -F: '{
    # EUI-64: U/L bit flipped, fffe inserted in the middle
    printf "fe80::%02x%s:%sff:fe%s:%s%s", xor(strtonum("0x" $1), 2), $2, $3, $4, $5, $6
  }' 2>/dev/null
}

while :; do
  # WITH THE DATE. The first version wrote only the time, which makes a log
  # spanning several days unreadable: a filter on a time range picks up every
  # day at once, and two interleaved evenings read as two competing samplers.
  # Seen, and believed, on 15 September. The field stays single because the
  # separator is a tab, so nothing that reads this file changes.
  now=$(date '+%Y-%m-%d %H:%M:%S')

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

  # Resolution, measured separately from the link: that is the whole question.
  if timeout 3 getent hosts github.com >/dev/null 2>&1; then dns=ok; else dns=ECHEC; fi

  ns=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf 2>/dev/null)
  rmt=$(date -r /etc/resolv.conf +%H:%M:%S 2>/dev/null)
  route="${g:--}"

  ad=$(sed -n 's/.*"state":"\([a-z]*\)".*/\1/p' \
        "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/airdropd/state.json" 2>/dev/null)
  vifs=$(ls /sys/class/net 2>/dev/null | grep -cE '^(go0|mon0|mon1|awdl0)$')

  # The path that actually carries AirDrop, measured on its own.
  p6=$(peer6)
  # A RATE, NOT A VERDICT. The first version sent two packets and wrote LOSS
  # if the first did not come back - so it gave the same word to a dead link and
  # to one losing 70% while still getting through. That is exactly the
  # difference we were trying to see. Six packets tell the two apart without
  # weighing on the link being measured.
  if [ -n "${p6:-}" ] && ip link show awdl0 >/dev/null 2>&1; then
    out=$(timeout 6 ping -6 -c6 -W1 -i 0.3 "$p6%awdl0" 2>/dev/null)
    pair=$(printf '%s' "$out" | grep -oE '[0-9]+% packet loss' | grep -oE '^[0-9]+')
    pair="${pair:-100}%"
    awdl_ms=$(printf '%s' "$out" | awk -F'/' '/rtt|round-trip/{printf "%.0f", $5}')
    awdl_ms="${awdl_ms:--}"
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
