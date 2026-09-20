"""The notch window: a layer-shell surface anchored at the top, centred.

Two things were established by measurement before this file was written,
because they decide the whole architecture:

1. A GTK4 window grows but never shrinks on its own. Only
   `set_default_size()` with explicit values brings the layer-shell surface
   back down. That is the recipe in `resize_to()`.
2. `Gdk.Surface.set_input_region()` is overwritten by GTK on Wayland. A large
   transparent surface with a clickable hole in it is therefore impossible:
   the surface must be exactly the size of the visible notch. That is what
   makes hovering reliable -- entering the surface is entering the notch.
"""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LS  # noqa: E402

from ..integrations import mpris
from ..theme import waybar
from ..widgets.calendar import CalendarWidget
from ..widgets.files import FilesWidget
from ..widgets.media import MediaWidget
from ..widgets.system import SystemWidget
from ..widgets.airdrop import AirDropWidget
from ..widgets.notes import NotesWidget

# Glyphs taken as they were from the old waybar mpris module, so the pill
# still looks the same to the eye.
DND_LOG = os.path.expanduser("~/.cache/hyprnotch/dnd.log")


def dnd_log(message):
    """Traces drag and drop events. Nothing else writes here: the file only
    grows on a drop, and it exists to diagnose what a source application
    actually offers."""
    try:
        os.makedirs(os.path.dirname(DND_LOG), exist_ok=True)
        with open(DND_LOG, "a", encoding="utf-8") as fh:
            fh.write(message + "\n")
    except OSError:
        pass


def paths_from_value(value):
    """Extracts paths, whatever shape they arrive in."""
    if isinstance(value, Gdk.FileList):
        return [f.get_path() for f in value.get_files() if f.get_path()]
    if isinstance(value, Gio.File):
        path = value.get_path()
        return [path] if path else []
    if isinstance(value, str):
        out = []
        for line in value.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            gfile = Gio.File.new_for_uri(line) if "://" in line else Gio.File.new_for_path(line)
            path = gfile.get_path()
            if path:
                out.append(path)
        return out
    return []


PLAYER_GLYPH = {
    "spotify": "\uf1bc", "firefox": "\uf269", "chromium": "\uf268",
    "mpv": "\U000f0439", "vlc": "\U000f057c", "mopidy": "\uf001",
}
DEFAULT_GLYPH = "\uf01d"
PAUSED_GLYPH = "\U000f040e"

SHELL_BORDER = 1       # la bordure de .nk-shell, en haut comme en bas

GHOST_WIDTH = 150      # cible de survol quand rien ne joue : invisible, donc large
COMPACT_MIN = 64       # plancher de la pastille quand elle porte du texte
COMPACT_MAX = 430
PILL_SPACING = 7       # l'espace entre le glyphe et le titre

PAGES = (
    ("calendar", "x-office-calendar-symbolic"),
    ("system", "system-run-symbolic"),
    ("files", "folder-symbolic"),
    ("airdrop", "send-to-symbolic"),
    ("notes", "view-list-bullet-symbolic"),
)


class Notch(Gtk.ApplicationWindow):
    def __init__(self, app, config, media, lang="fr"):
        super().__init__(application=app)
        self.config = config
        self.media = media
        self.lang = lang

        self.compact_size = tuple(config.get("appearance", "compact", default=[230, 30]))
        self.expanded_size = tuple(config.get("appearance", "expanded", default=[660, 224]))
        self.close_delay = config.get("notch", "close_delay_ms", default=180)
        self.hover_opens = config.get("notch", "hover_to_open", default=True)

        self.open = False
        self.pinned = False
        # Pinned *for typing*, which is not the same as holding the keyboard:
        # only the former has to let go when the compositor hands the keyboard
        # to someone else.
        self.editing = False
        self.hovered = False
        # The last keyboard mode asked of the compositor. Remembered so the
        # request is not re-issued on every mouse movement.
        self.kb_mode = None
        self.close_source = None
        self.bar = waybar.read_bar()
        self.island = waybar.island_metrics()
        self._realign_source = None

        self.add_css_class("nk-root")
        self._build()
        self._layer_shell()
        self._controllers()
        self.resize_to(*self.compact_size)
        # With no content (nothing playing) no layout is triggered at all and
        # the surface stays at GTK's fallback size, 200x200. Reassert the size
        # once the window is mapped.
        self.connect("map", lambda *_: self.resize_to(*self._compact_geometry()))

        target = Adw.CallbackAnimationTarget.new(self._on_frame)
        self.anim = Adw.TimedAnimation.new(
            self, 0.0, 1.0, config.get("appearance", "animation_ms", default=260), target)
        self.anim.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self.anim.connect("done", lambda *_: self._update_ghost())

    # --- construction ---------------------------------------------------
    def _build(self):
        self.shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.shell.add_css_class("nk-shell")
        self.shell.set_overflow(Gtk.Overflow.HIDDEN)

        # The ScrolledWindow is not there to scroll: it cuts the propagation
        # of the minimum size, without which expanded content would stop the
        # shell from shrinking.
        self.clip = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
            vscrollbar_policy=Gtk.PolicyType.EXTERNAL,
            propagate_natural_width=False, propagate_natural_height=False,
            kinetic_scrolling=False, hexpand=True, vexpand=True)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               transition_duration=170,
                               hhomogeneous=False, vhomogeneous=False)
        self.stack.add_named(self._compact_view(), "compact")
        self.stack.add_named(self._expanded_view(), "expanded")
        self.stack.set_visible_child_name("compact")

        self.clip.set_child(self.stack)
        self.shell.append(self.clip)

        # The surface reaches up to y=0 and the offset under the bar is
        # recreated HERE, with a spacer, instead of being a layer-shell margin.
        # With the margin, the strip above the notch did not belong to the
        # surface: moving the mouse to the very top of the screen left it,
        # which closed the panel just as you were aiming for the bar.
        self.lift = Gtk.Box()
        self.lift.set_size_request(-1, self._island_top())
        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        holder.append(self.lift)
        holder.append(self.shell)
        self.set_child(holder)

    def _compact_view(self):
        # Content centred, and the pill sizes itself to it: that is what makes
        # it look like the old module, which had no fixed width.
        box = Gtk.Box(spacing=7, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        box.add_css_class("nk-pill")
        box.set_size_request(-1, self._pill_height())

        # Two possible headers: the cover art when we have it, otherwise the
        # player's glyph. Only one of the two is ever visible.
        self.pulse = Gtk.Label()
        self.pulse.add_css_class("nk-glyph")

        side = self._thumb_size()
        self.thumb = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        self.thumb.set_size_request(side, side)
        thumb_clip = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
            vscrollbar_policy=Gtk.PolicyType.EXTERNAL,
            propagate_natural_width=False, propagate_natural_height=False,
            kinetic_scrolling=False)
        thumb_clip.set_size_request(side, side)
        thumb_clip.set_child(self.thumb)
        self.thumb_frame = Gtk.Box(valign=Gtk.Align.CENTER)
        self.thumb_frame.add_css_class("nk-thumb")
        self.thumb_frame.set_overflow(Gtk.Overflow.HIDDEN)
        self.thumb_frame.set_size_request(side, side)
        self.thumb_frame.append(thumb_clip)
        self.thumb_frame.set_visible(False)
        self.thumb_for = None

        self.c_title = Gtk.Label(ellipsize=3)
        self.c_title.add_css_class("nk-compact-title")
        box.append(self.pulse)
        box.append(self.thumb_frame)
        box.append(self.c_title)
        self.compact = box
        return box

    def _pill_height(self):
        """Usable height inside the shell.

        The shell has a one-pixel border top and bottom: asking for the full
        height shifted all the content down by a pixel, which showed up most
        on the thumbnail."""
        return max(1, self._island_height() - 2 * SHELL_BORDER)

    def _thumb_size(self):
        """A thumbnail that fits the pill without making it grow."""
        return max(12, self._pill_height() - 6)

    def _expanded_view(self):
        box = Gtk.Box(spacing=14)
        box.add_css_class("nk-pad-lg")
        box.set_size_request(*self.expanded_size)

        self.w_media = MediaWidget(self.media, self.lang)
        self.w_media.set_hexpand(True)
        box.append(self.w_media)

        separator = Gtk.Box()
        separator.add_css_class("nk-sep")
        separator.set_size_request(1, -1)
        box.append(separator)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_size_request(268, -1)

        self.tabs = Gtk.Box(spacing=4, halign=Gtk.Align.END)
        self.page_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                                    transition_duration=140, vexpand=True)
        self.w_calendar = CalendarWidget(self.lang)
        self.w_system = SystemWidget(self.lang)
        self.w_files = FilesWidget(self.lang)
        self.w_airdrop = AirDropWidget(self.lang, shelf=self.w_files)
        self.w_notes = NotesWidget(self.lang, on_edit=self.pin_open,
                                   on_arm=self.arm_keyboard)
        self.page_stack.add_named(self.w_calendar, "calendar")
        self.page_stack.add_named(self.w_system, "system")
        self.page_stack.add_named(self.w_files, "files")
        self.page_stack.add_named(self.w_airdrop, "airdrop")
        self.page_stack.add_named(self.w_notes, "notes")

        self.tab_buttons = {}
        enabled = self.config.get("widgets", default={})
        for name, icon in PAGES:
            if not enabled.get(name, True):
                continue
            button = Gtk.Button()
            button.set_child(Gtk.Image.new_from_icon_name(icon))
            button.add_css_class("nk-tab")
            button.connect("clicked", lambda _b, n=name: self.show_page(n))
            self.tabs.append(button)
            self.tab_buttons[name] = button

        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_tab_scroll)
        self.tabs.add_controller(scroll)

        right.append(self.tabs)
        right.append(self.page_stack)
        box.append(right)

        wanted = self.config.get("notch", "default_page", default="calendar")
        if wanted not in self.tab_buttons:
            wanted = next(iter(self.tab_buttons), "calendar")
        self.show_page(wanted)
        return box

    # --- layer shell ----------------------------------------------------
    def _layer_shell(self):
        LS.init_for_window(self)
        LS.set_namespace(self, "hyprnotch")
        layer = LS.Layer.OVERLAY if self.config.get(
            "notch", "layer", default="top") == "overlay" else LS.Layer.TOP
        LS.set_layer(self, layer)
        LS.set_anchor(self, LS.Edge.TOP, True)
        self._set_kb(LS.KeyboardMode.NONE)
        # Exclusive zone at -1: the notch ignores waybar's own and sits on the
        # same strip, in the place of the mpris module.
        LS.set_exclusive_zone(self, -1 if self.config.get(
            "notch", "in_bar", default=True) else 0)
        LS.set_margin(self, LS.Edge.TOP, 0)

        wanted = self.config.get("notch", "monitor", default="primary")
        if wanted and wanted != "primary":
            monitors = Gdk.Display.get_default().get_monitors()
            for index in range(monitors.get_n_items()):
                monitor = monitors.get_item(index)
                if monitor.get_connector() == wanted:
                    LS.set_monitor(self, monitor)
                    break

    def _controllers(self):
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_enter)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

        # Accept all three ways a source can offer files: the GTK list, a lone
        # file, or raw text/uri-list. Taking only GdkFileList is enough for
        # Nautilus but not for everything.
        drop = Gtk.DropTarget(actions=Gdk.DragAction.COPY)
        drop.set_gtypes([Gdk.FileList, Gio.File, GObject.TYPE_STRING])
        drop.set_preload(True)
        drop.connect("accept", self._on_drag_accept)
        drop.connect("enter", self._on_drag_enter)
        drop.connect("motion", self._on_drag_motion)
        drop.connect("drop", self._on_drop)
        self.add_controller(drop)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        # Keyboard focus lost: the compositor has served someone else.
        self.connect("notify::is-active", self._on_active)

    def _on_drag_accept(self, _target, drop):
        formats = drop.get_formats()
        dnd_log(f"accept: {formats.to_string()}")
        return True

    def _on_drag_enter(self, _target, _x, _y):
        dnd_log("enter")
        self._cancel_close()
        self.expand(instant=True)
        self.show_page("files")
        return Gdk.DragAction.COPY

    def _on_drag_motion(self, _target, _x, _y):
        return Gdk.DragAction.COPY

    def _on_drop(self, _target, value, _x, _y):
        dnd_log(f"drop: {type(value)} {value!r:.120}")
        paths = paths_from_value(value)
        dnd_log(f"  -> {paths}")
        if not paths:
            return False
        self.w_files.add(paths)
        self.expand()
        self.show_page("files")
        return True

    # --- size and animation ---------------------------------------------
    def resize_to(self, width, height):
        """The only combination that both grows and shrinks a layer-shell
        surface (measured, see the header).

        The window is taller than the shell by the height of the spacer that
        replaces the old layer-shell margin."""
        self.shell.set_size_request(width, height)
        self.set_default_size(width, height + self._island_top())

    def _on_frame(self, value):
        progress = value if self.open else 1.0 - value
        cw, ch = self._compact_geometry()
        ew, eh = self.expanded_size
        self.resize_to(int(cw + (ew - cw) * progress),
                       int(ch + (eh - ch) * progress))

    def expand(self, instant=False):
        if self.open:
            return
        self.open = True
        self.shell.remove_css_class("nk-ghost")
        self.stack.set_visible_child_name("expanded")
        self._set_live(True)
        if instant:
            # During a drag and drop, open in one step: twenty resizes of the
            # surface under the cursor while the compositor is tracking the
            # drag is asking for trouble.
            self.resize_to(*self.expanded_size)
            return
        self.anim.play()

    def collapse(self):
        if not self.open or self.pinned:
            return
        self.open = False
        # The notch is closing: nothing in it is waiting for a keystroke.
        self._set_kb(LS.KeyboardMode.NONE)
        self.stack.set_visible_child_name("compact")
        self._set_live(False)
        # Going ghost waits for the animation to finish: otherwise the shell
        # loses its background while the surface is still shrinking, and the
        # panel's text is seen floating on the desktop for a fraction of a
        # second.
        self.anim.play()

    def toggle(self):
        if self.open:
            self.editing = False
            self.pinned = False
            self.collapse()
        else:
            self.pinned = True
            self._set_kb(LS.KeyboardMode.ON_DEMAND)
            self.expand()

    def _set_kb(self, mode):
        """One wayland request per actual change, not per movement."""
        if self.kb_mode == mode:
            return
        self.kb_mode = mode
        LS.set_keyboard_mode(self, mode)

    def arm_keyboard(self, on):
        """The pointer enters or leaves an input area.

        Under layer-shell, `ON_DEMAND` does not say "take the keyboard" but
        "the compositor will give it to you on the next click". Arming it
        during the click is therefore too late: that click has already been
        resolved under the old mode, and a second one was needed for nothing.
        We arm on hover, before the click arrives."""
        if self.editing:
            return
        self._set_kb(LS.KeyboardMode.ON_DEMAND if on else LS.KeyboardMode.NONE)

    def pin_open(self):
        """A widget is claiming the keyboard -- something is being typed into.
        The notch stops closing on mouse movement until Escape is pressed."""
        self.editing = True
        self.pinned = True
        self._set_kb(LS.KeyboardMode.ON_DEMAND)

    def _on_active(self, *_):
        """The compositor has just given the keyboard to another window.

        Without this the notch stayed pinned, and so open, but with no
        keyboard: a panel very much alive on screen that listened to nothing
        any more and had to be clicked again to wake. We let go rather than
        lie about the state."""
        if self.props.is_active or not self.editing:
            return
        self.release_edit()

    def release_edit(self):
        """Saves the note being edited, gives the keyboard back, and lets
        hover take over again. If the mouse has already left, close."""
        if not self.editing:
            return
        self.w_notes.flush()
        self.editing = False
        self.pinned = False
        self._set_kb(LS.KeyboardMode.NONE)
        if not self.hovered:
            self._cancel_close()
            self.close_source = GLib.timeout_add(self.close_delay,
                                                 self._deferred_close)

    def _set_live(self, live):
        self.w_media.set_live(live)
        page = self.page_stack.get_visible_child_name()
        self.w_system.set_live(live and page == "system")
        self.w_airdrop.set_live(live and page == "airdrop")
        self.w_notes.set_live(live and page == "notes")
        if live:
            self.w_calendar.refresh()

    def show_page(self, name):
        if name not in self.tab_buttons:
            return
        self.page_stack.set_visible_child_name(name)
        for key, button in self.tab_buttons.items():
            if key == name:
                button.add_css_class("nk-on")
            else:
                button.remove_css_class("nk-on")
        self.w_system.set_live(self.open and name == "system")
        self.w_airdrop.set_live(self.open and name == "airdrop")
        self.w_notes.set_live(self.open and name == "notes")
        if name == "calendar":
            self.w_calendar.refresh()

    def _on_tab_scroll(self, _controller, _dx, dy):
        names = list(self.tab_buttons)
        if not names:
            return False
        current = self.page_stack.get_visible_child_name()
        index = names.index(current) if current in names else 0
        self.show_page(names[(index + (1 if dy > 0 else -1)) % len(names)])
        return True

    # --- interactions ---------------------------------------------------
    def _on_enter(self, *_):
        self.hovered = True
        self._cancel_close()
        if self.hover_opens:
            self.expand()

    def _on_leave(self, *_):
        self.hovered = False
        if self.pinned:
            return
        self._cancel_close()
        self.close_source = GLib.timeout_add(self.close_delay, self._deferred_close)

    def _deferred_close(self):
        self.close_source = None
        self.collapse()
        return False

    def _cancel_close(self):
        if self.close_source is not None:
            GLib.source_remove(self.close_source)
            self.close_source = None

    def _on_key(self, _controller, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            if self.editing:
                self.w_notes.flush()
            self.editing = False
            self.pinned = False
            self._set_kb(LS.KeyboardMode.NONE)
            self.collapse()
            return True
        return False

    # --- rendering ------------------------------------------------------
    def refresh(self):
        self.w_media.refresh()
        self._refresh_compact()

    def _refresh_compact(self):
        """With nothing playing the pill shows nothing and draws nothing: what
        remains is an invisible area, still hoverable."""
        active = self.media.active
        self.c_title.set_visible(active)
        if active:
            track = self.media.track
            playing = self.media.playing
            source = (self.media.source or "").lower()
            self.pulse.set_text(PLAYER_GLYPH.get(source, DEFAULT_GLYPH) if playing
                                else PAUSED_GLYPH)
            label = " ".join(part for part in (track.artist, track.title) if part)
            self.c_title.set_text(label[:50])
            self._refresh_thumb(track)
        else:
            self.pulse.set_text("")
            self.c_title.set_text("")
            self.thumb_for = None
            self.thumb_frame.set_visible(False)
        self.pulse.set_visible(active and not self.thumb_frame.get_visible())
        self._update_ghost()
        if not self.open:
            self.resize_to(*self._compact_geometry())

    def _island_top(self):
        offset = self.config.get("notch", "margin_top", default=0)
        if self.island:
            return self.island["top"] + offset
        return self.bar.get("margin_top", 1) + 1 + offset

    def _island_height(self):
        """Height of a waybar pill, measured on the bar itself."""
        if self.island:
            return self.island["height"]
        return self.compact_size[1]

    def _compact_geometry(self):
        """The pill fits its text, bounded so it never eats the bar nor
        becomes impossible to find by hovering.

        Measured through a fresh Pango layout rather than measure(): a label
        with ellipsize reports a truncated natural width, and the pill would
        have cut itself short."""
        _min_h, natural, _a, _b = self.compact.measure(Gtk.Orientation.VERTICAL, -1)
        height = max(natural, self._island_height(), 1)
        if not self.media.active:
            return GHOST_WIDTH, height
        text = self.c_title.get_text()
        width = 2 * self.bar.get("pad_x", 10) + 2
        if self.thumb_frame.get_visible():
            lead = self._thumb_size()
        else:
            glyph = self.pulse.get_text()
            lead = self.pulse.create_pango_layout(glyph).get_pixel_size()[0] if glyph else 0
        width += lead
        if text:
            width += self.c_title.create_pango_layout(text).get_pixel_size()[0]
            if lead:
                width += PILL_SPACING
        return max(COMPACT_MIN, min(COMPACT_MAX, width)), height

    def _refresh_thumb(self, track):
        """The cover art replaces the glyph when the player provides one. With
        no cover art -- many sources publish none -- we keep the application's
        logo."""
        key = track.art_url or track.trackid
        if key == self.thumb_for:
            return
        self.thumb_for = key
        if not track.art_url:
            self.thumb_frame.set_visible(False)
            self.pulse.set_visible(True)
            return
        mpris.fetch_art(track.art_url, self._set_thumb)

    def _set_thumb(self, path):
        try:
            self.thumb.set_filename(path)
        except GLib.Error:
            return
        self.thumb_frame.set_visible(True)
        self.pulse.set_visible(False)
        if not self.open:
            self.resize_to(*self._compact_geometry())

    def _update_ghost(self):
        if not self.open and not self.media.active:
            self.shell.add_css_class("nk-ghost")
        else:
            self.shell.remove_css_class("nk-ghost")

    def _align_to_bar(self):
        """Takes the height and position of one of waybar's pills."""
        island = waybar.island_metrics()
        if island is None:
            # The bar is restarting: keep the current alignment rather than
            # fall back on a default value.
            return False
        self.bar = waybar.read_bar()
        self.island = island
        self.compact.set_size_request(-1, self._pill_height())
        # The spacer carries the offset, not the layer-shell margin: it is the
        # spacer that has to be readjusted when the bar changes height.
        self.lift.set_size_request(-1, self._island_top())
        if not self.open:
            self.resize_to(*self._compact_geometry())
        return False

    def reload_theme(self):
        """HyprSettings may just have changed the bar: re-read its metrics and
        realign to them.

        The file changes before waybar restarts, so on the first pass it still
        has its old size. We come back for a few seconds, long enough for it
        to reappear."""
        self.w_notes.reload_theme()
        self._align_to_bar()
        self._realign_left = 20
        if self._realign_source is None:
            self._realign_source = GLib.timeout_add(400, self._realign_tick)
        self.refresh()

    def _realign_tick(self):
        self._align_to_bar()
        self._realign_left -= 1
        if self._realign_left > 0:
            return True
        self._realign_source = None
        return False
