"""MPRIS via Playerctl.

Tout passe par des signaux : on ne demande jamais « quel est le morceau ? »
en boucle. Seule la position n'a pas de signal utilisable — elle est donc
sondée, mais uniquement quand le panneau est ouvert (voir MediaWidget).
"""

import hashlib
import os
import threading
import urllib.request

import gi

gi.require_version("Playerctl", "2.0")
from gi.repository import GLib, Playerctl  # noqa: E402

CACHE = os.path.expanduser("~/.cache/hyprnotch/art")

# Les lecteurs qu'on refuse de suivre : ils publient un MPRIS parasite.
IGNORED = ("kdeconnect", "playerctld")

# Playerctl expose des enums : leur str() donne un entier, pas un nom.
STATUS = {
    Playerctl.PlaybackStatus.PLAYING: "playing",
    Playerctl.PlaybackStatus.PAUSED: "paused",
    Playerctl.PlaybackStatus.STOPPED: "stopped",
}
LOOP = {
    Playerctl.LoopStatus.NONE: "none",
    Playerctl.LoopStatus.TRACK: "track",
    Playerctl.LoopStatus.PLAYLIST: "playlist",
}


def status_of(player):
    return STATUS.get(player.props.playback_status, "stopped")


class Track:
    __slots__ = ("title", "artist", "album", "art_url", "length", "trackid")

    def __init__(self):
        self.title = self.artist = self.album = ""
        self.art_url = None
        self.length = 0
        self.trackid = ""

    @property
    def empty(self):
        return not self.title and not self.artist


class Media:
    """Suit le lecteur actif et prévient l'UI. `on_update` est appelé dans
    la boucle principale GTK."""

    def __init__(self, on_update):
        self.on_update = on_update
        self.player = None
        self.track = Track()
        self.status = "stopped"
        self.shuffle = False
        self.loop = "none"

        self.manager = Playerctl.PlayerManager()
        self.manager.connect("name-appeared", self._appeared)
        self.manager.connect("player-vanished", self._vanished)
        for name in self.manager.props.player_names:
            self._attach(name)

    # --- gestion du lecteur actif ---------------------------------------
    def _appeared(self, _mgr, name):
        self._attach(name)

    def _vanished(self, _mgr, _player):
        self.player = None
        for name in self.manager.props.player_names:
            if self._attach(name):
                return
        self.track = Track()
        self.status = "stopped"
        self._emit()

    def _attach(self, name):
        if any(bad in name.name.lower() for bad in IGNORED):
            return False
        try:
            player = Playerctl.Player.new_from_name(name)
        except GLib.Error:
            return False
        player.connect("metadata", lambda p, m: self._sync(p))
        player.connect("playback-status", lambda p, s: self._sync(p))
        player.connect("shuffle", lambda p, v: self._sync(p))
        player.connect("loop-status", lambda p, v: self._sync(p))
        self.manager.manage_player(player)
        # Un lecteur qui joue prend la main sur un lecteur en pause.
        if self.player is None or status_of(player) == "playing":
            self.player = player
        self._sync(self.player)
        return True

    def _sync(self, player):
        if player is None:
            return
        # Le lecteur qui vient de passer en lecture devient l'actif.
        if status_of(player) == "playing":
            self.player = player
        if player is not self.player:
            return

        meta = player.props.metadata
        track = Track()
        try:
            keys = meta.keys()
            if "xesam:title" in keys:
                track.title = str(meta["xesam:title"])
            if "xesam:artist" in keys:
                value = meta["xesam:artist"]
                unpacked = value.unpack() if hasattr(value, "unpack") else value
                track.artist = ", ".join(unpacked) if isinstance(unpacked, list) else str(unpacked)
            if "xesam:album" in keys:
                track.album = str(meta["xesam:album"])
            if "mpris:artUrl" in keys:
                track.art_url = str(meta["mpris:artUrl"])
            if "mpris:length" in keys:
                track.length = int(meta["mpris:length"])
            if "mpris:trackid" in keys:
                track.trackid = str(meta["mpris:trackid"])
        except (AttributeError, TypeError, ValueError):
            pass

        self.track = track
        self.status = status_of(player)
        self.shuffle = bool(player.props.shuffle)
        self.loop = LOOP.get(player.props.loop_status, "none")
        self._emit()

    def _emit(self):
        GLib.idle_add(self.on_update)

    # --- lecture --------------------------------------------------------
    @property
    def active(self):
        return self.player is not None and not self.track.empty

    @property
    def playing(self):
        return self.status == "playing"

    @property
    def source(self):
        if self.player is None:
            return ""
        return (self.player.props.player_name or "").capitalize()

    def position(self):
        if self.player is None:
            return 0
        try:
            return int(self.player.props.position)
        except (GLib.Error, AttributeError):
            return 0

    def _call(self, verb, *args):
        if self.player is None:
            return
        try:
            getattr(self.player, verb)(*args)
        except GLib.Error:
            pass

    def play_pause(self):
        self._call("play_pause")

    def next(self):
        self._call("next")

    def previous(self):
        self._call("previous")

    def seek_to(self, micros):
        if self.player is None:
            return
        try:
            self.player.set_position(int(micros))
        except GLib.Error:
            pass

    def toggle_shuffle(self):
        if self.player is None:
            return
        try:
            self.player.set_shuffle(not self.shuffle)
        except GLib.Error:
            pass

    def cycle_loop(self):
        if self.player is None:
            return
        order = {"none": Playerctl.LoopStatus.PLAYLIST,
                 "playlist": Playerctl.LoopStatus.TRACK,
                 "track": Playerctl.LoopStatus.NONE}
        try:
            self.player.set_loop_status(order.get(self.loop, Playerctl.LoopStatus.NONE))
        except GLib.Error:
            pass

    def can(self, what):
        if self.player is None:
            return False
        return bool(getattr(self.player.props, what, False))


def fetch_art(url, done):
    """Télécharge la pochette une fois, la garde en cache, puis rappelle
    `done(chemin)` dans la boucle GTK."""
    if not url:
        return
    if url.startswith("file://"):
        GLib.idle_add(done, url[7:])
        return

    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest())
    if os.path.exists(path):
        GLib.idle_add(done, path)
        return

    def work():
        try:
            os.makedirs(CACHE, exist_ok=True)
            with urllib.request.urlopen(url, timeout=8) as response:
                data = response.read()
            tmp = path + ".part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
            GLib.idle_add(done, path)
        except Exception:
            pass

    threading.Thread(target=work, daemon=True).start()
