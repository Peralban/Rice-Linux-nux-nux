"""Widget média : pochette, titre, progression, contrôles.

Ne connaît rien à Spotify. Il parle au service MPRIS, qui suit le lecteur
actif, quel qu'il soit.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from ..integrations import mpris

COVER = 108
TICK_MS = 1000

STRINGS = {
    "fr": {"idle": "Rien en lecture", "idle_sub": "Lance un morceau, il apparaîtra ici",
           "prev": "Précédent", "play": "Lecture", "pause": "Pause", "next": "Suivant",
           "shuffle": "Aléatoire", "loop_none": "Répétition",
           "loop_playlist": "Répéter la playlist", "loop_track": "Répéter le morceau"},
    "en": {"idle": "Nothing playing", "idle_sub": "Start a track and it shows up here",
           "prev": "Previous", "play": "Play", "pause": "Pause", "next": "Next",
           "shuffle": "Shuffle", "loop_none": "Repeat",
           "loop_playlist": "Repeat playlist", "loop_track": "Repeat track"},
}


# La boucle a deux états actifs, pas un : « playlist » et « morceau » se
# ressemblaient tant que seule la couleur les signalait. L'icône les sépare.
LOOP_ICON = {
    "none": "media-playlist-repeat-symbolic",
    "playlist": "media-playlist-repeat-symbolic",
    "track": "media-playlist-repeat-song-symbolic",
}


def clock(micros):
    seconds = max(0, int(micros // 1_000_000))
    return f"{seconds // 60}:{seconds % 60:02d}"


class MediaWidget(Gtk.Box):
    def __init__(self, media, lang="fr"):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.media = media
        self.s = STRINGS.get(lang, STRINGS["fr"])
        self.live = False
        self.tick = None
        self.art_for = None
        self.seeking = False

        # --- pochette ---
        self.cover_frame = Gtk.Box(valign=Gtk.Align.CENTER)
        self.cover_frame.add_css_class("nk-cover")
        self.cover_frame.set_size_request(COVER, COVER)
        self.cover_frame.set_overflow(Gtk.Overflow.HIDDEN)
        self.cover = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        self.cover.set_size_request(COVER, COVER)
        # La taille naturelle d'une Picture est celle de la texture : sans
        # cette coupure de propagation, la pochette grossissait ou rétrécissait
        # selon la place laissée par le titre.
        clip = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
            vscrollbar_policy=Gtk.PolicyType.EXTERNAL,
            propagate_natural_width=False, propagate_natural_height=False,
            kinetic_scrolling=False)
        clip.set_size_request(COVER, COVER)
        clip.set_child(self.cover)
        self.cover_frame.append(clip)

        overlay = Gtk.Overlay(valign=Gtk.Align.CENTER)
        overlay.set_child(self.cover_frame)
        self.badge = Gtk.Image(pixel_size=16, halign=Gtk.Align.END, valign=Gtk.Align.END)
        self.badge.add_css_class("nk-cover-badge")
        self.badge.set_margin_end(4)
        self.badge.set_margin_bottom(4)
        overlay.add_overlay(self.badge)
        self.append(overlay)

        # --- colonne texte ---
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                         valign=Gtk.Align.CENTER, hexpand=True)

        self.title = Gtk.Label(xalign=0, ellipsize=3)
        self.title.add_css_class("nk-title")
        self.artist = Gtk.Label(xalign=0, ellipsize=3)
        self.artist.add_css_class("nk-artist")
        column.append(self.title)
        column.append(self.artist)

        self.scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                               adjustment=Gtk.Adjustment(lower=0, upper=1, value=0),
                               draw_value=False, hexpand=True)
        self.scale.add_css_class("nk-scale")
        self.scale.set_margin_top(8)
        self.scale.connect("change-value", self._on_seek)
        column.append(self.scale)

        times = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.elapsed = Gtk.Label(xalign=0)
        self.elapsed.add_css_class("nk-meta")
        self.total = Gtk.Label(xalign=1, hexpand=True)
        self.total.add_css_class("nk-meta")
        times.append(self.elapsed)
        times.append(self.total)
        column.append(times)

        # --- contrôles ---
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                           halign=Gtk.Align.CENTER)
        controls.set_margin_top(8)
        self.b_shuffle = self._button("media-playlist-shuffle-symbolic",
                                      self.s["shuffle"], self.media.toggle_shuffle)
        self.b_prev = self._button("media-skip-backward-symbolic",
                                   self.s["prev"], self.media.previous)
        self.b_play = self._button("media-playback-start-symbolic",
                                   self.s["play"], self.media.play_pause, big=True)
        self.b_next = self._button("media-skip-forward-symbolic",
                                   self.s["next"], self.media.next)
        self.b_loop = self._button(LOOP_ICON["none"],
                                   self.s["loop_none"], self.media.cycle_loop)
        for widget in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_loop):
            controls.append(widget)
        column.append(controls)

        self.append(column)

        # --- état vide ---
        self.idle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                            valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER, hexpand=True)
        idle_icon = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
        idle_icon.set_pixel_size(22)
        idle_icon.add_css_class("nk-meta")
        title = Gtk.Label(label=self.s["idle"])
        title.add_css_class("nk-empty")
        subtitle = Gtk.Label(label=self.s["idle_sub"])
        subtitle.add_css_class("nk-meta")
        for widget in (idle_icon, title, subtitle):
            self.idle.append(widget)
        self.append(self.idle)

    def _button(self, icon, tooltip, action, big=False):
        button = Gtk.Button(tooltip_text=tooltip)
        button.set_child(Gtk.Image.new_from_icon_name(icon))
        button.add_css_class("nk-ctl")
        if big:
            button.add_css_class("nk-play")
        button.connect("clicked", lambda *_: action())
        return button

    # --- cycle de vie ---------------------------------------------------
    def set_live(self, live):
        """La position n'a pas de signal MPRIS : on ne la sonde que pendant
        que le panneau est ouvert."""
        self.live = live
        if live and self.tick is None:
            self.tick = GLib.timeout_add(TICK_MS, self._on_tick)
            self._on_tick()
        elif not live and self.tick is not None:
            GLib.source_remove(self.tick)
            self.tick = None

    def _on_tick(self):
        if not self.live:
            self.tick = None
            return False
        self._refresh_position()
        return True

    def _on_seek(self, _scale, _scroll, value):
        length = self.media.track.length
        if length:
            self.media.seek_to(max(0, min(length, value * length)))
        return False

    def _refresh_position(self):
        track = self.media.track
        if not track.length:
            self.scale.set_sensitive(False)
            self.elapsed.set_text("")
            self.total.set_text("")
            return
        position = self.media.position()
        self.scale.set_sensitive(True)
        self.scale.set_value(min(1.0, position / track.length))
        self.elapsed.set_text(clock(position))
        self.total.set_text(clock(track.length))

    # --- rendu ----------------------------------------------------------
    def refresh(self):
        active = self.media.active
        self.idle.set_visible(not active)
        for widget in list(self):
            if widget is not self.idle:
                widget.set_visible(active)
        if not active:
            self.art_for = None
            return

        track = self.media.track
        self.title.set_text(track.title or "—")
        self.artist.set_text(track.artist or track.album or "")
        self.title.set_tooltip_text(track.title)

        playing = self.media.playing
        image = self.b_play.get_child()
        image.set_from_icon_name(
            "media-playback-pause-symbolic" if playing else "media-playback-start-symbolic")
        self.b_play.set_tooltip_text(self.s["pause"] if playing else self.s["play"])

        self.b_prev.set_sensitive(self.media.can("can_go_previous"))
        self.b_next.set_sensitive(self.media.can("can_go_next"))
        self._toggle_class(self.b_shuffle, self.media.shuffle)
        loop = self.media.loop
        self.b_loop.get_child().set_from_icon_name(LOOP_ICON.get(loop, LOOP_ICON["none"]))
        self.b_loop.set_tooltip_text(self.s.get(f"loop_{loop}", self.s["loop_none"]))
        self._toggle_class(self.b_loop, loop != "none")

        self._refresh_badge()
        self._refresh_art(track)
        self._refresh_position()

    @staticmethod
    def _toggle_class(widget, on):
        if on:
            widget.add_css_class("nk-on")
        else:
            widget.remove_css_class("nk-on")

    def _refresh_badge(self):
        name = (self.media.source or "").lower()
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        for candidate in (name, f"{name}-symbolic", "audio-x-generic-symbolic"):
            if candidate and theme.has_icon(candidate):
                self.badge.set_from_icon_name(candidate)
                self.badge.set_visible(True)
                self.badge.set_tooltip_text(self.media.source)
                return
        self.badge.set_visible(False)

    def _refresh_art(self, track):
        key = track.art_url or track.trackid
        if key == self.art_for:
            return
        self.art_for = key
        if not track.art_url:
            self.cover.set_paintable(None)
            return
        mpris.fetch_art(track.art_url, self._set_art)

    def _set_art(self, path):
        try:
            self.cover.set_filename(path)
        except GLib.Error:
            self.cover.set_paintable(None)
