#!/bin/zsh
# Restarts the bar and the notification daemon.
#
# `setsid -f` rather than a bare `&`: the replacement has to outlive this
# script. Backgrounded this way it stays in the dispatcher's process group,
# and goes down with it.

killall -9 swaync
killall -9 waybar

setsid -f swaync >/dev/null 2>&1
setsid -f waybar >/dev/null 2>&1
