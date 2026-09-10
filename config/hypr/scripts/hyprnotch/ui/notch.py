"""La fenêtre notch : surface layer-shell ancrée en haut, centrée.

Deux points ont été établis à la mesure avant d'écrire ce fichier, parce
qu'ils décident de toute l'architecture :

1. Une fenêtre GTK4 grandit mais ne rétrécit jamais toute seule. Seul
   `set_default_size()` avec des valeurs explicites fait redescendre la
   surface layer-shell. C'est la recette de `resize_to()`.
2. `Gdk.Surface.set_input_region()` est réécrit par GTK sur Wayland. Une
   grande surface transparente avec un trou cliquable est donc impossible :
   la surface doit faire exactement la taille du notch visible. C'est ce
   qui rend le survol fiable — entrer dans la surface, c'est entrer dans
   le notch.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LS  # noqa: E402

from ..widgets.calendar import CalendarWidget
from ..widgets.media import MediaWidget
from ..widgets.notifications import NotificationsWidget
from ..widgets.system import SystemWidget

PAGES = (
    ("calendar", "x-office-calendar-symbolic"),
    ("system", "system-run-symbolic"),
    ("notifications", "preferences-system-notifications-symbolic"),
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
        self.close_source = None

        self.add_css_class("nk-root")
        self._build()
        self._layer_shell()
        self._controllers()
        self.resize_to(*self.compact_size)

        target = Adw.CallbackAnimationTarget.new(self._on_frame)
        self.anim = Adw.TimedAnimation.new(
            self, 0.0, 1.0, config.get("appearance", "animation_ms", default=260), target)
        self.anim.set_easing(Adw.Easing.EASE_OUT_CUBIC)

    # --- construction ---------------------------------------------------
    def _build(self):
        self.shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.shell.add_css_class("nk-shell")
        self.shell.set_overflow(Gtk.Overflow.HIDDEN)

        # Le ScrolledWindow ne sert pas à défiler : il coupe la propagation
        # de la taille minimale, sans quoi le contenu déplié empêcherait la
        # coque de rétrécir.
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
        self.set_child(self.shell)

    def _compact_view(self):
        box = Gtk.Box(spacing=8, valign=Gtk.Align.START)
        box.add_css_class("nk-pad")
        box.set_size_request(*self.compact_size)

        self.pulse = Gtk.Label(label="●")
        self.pulse.add_css_class("nk-pulse")
        self.c_title = Gtk.Label(xalign=0, ellipsize=3, hexpand=True)
        self.c_title.add_css_class("nk-compact-title")
        self.c_right = Gtk.Label(xalign=1)
        self.c_right.add_css_class("nk-compact-sub")
        for widget in (self.pulse, self.c_title, self.c_right):
            box.append(widget)
        return box

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
        self.w_notifications = NotificationsWidget(self.lang)
        self.page_stack.add_named(self.w_calendar, "calendar")
        self.page_stack.add_named(self.w_system, "system")
        self.page_stack.add_named(self.w_notifications, "notifications")

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
        LS.set_keyboard_mode(self, LS.KeyboardMode.NONE)
        LS.set_exclusive_zone(self, 0)
        LS.set_margin(self, LS.Edge.TOP, self.config.get("notch", "margin_top", default=0))

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

        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.add_controller(click)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

    # --- taille et animation --------------------------------------------
    def resize_to(self, width, height):
        """La seule combinaison qui fasse aussi bien grandir que rétrécir
        une surface layer-shell (mesuré, voir l'en-tête)."""
        self.shell.set_size_request(width, height)
        self.set_default_size(width, height)

    def _on_frame(self, value):
        progress = value if self.open else 1.0 - value
        cw, ch = self.compact_size
        ew, eh = self.expanded_size
        self.resize_to(int(cw + (ew - cw) * progress),
                       int(ch + (eh - ch) * progress))

    def expand(self):
        if self.open:
            return
        self.open = True
        self.stack.set_visible_child_name("expanded")
        self._set_live(True)
        self.anim.play()

    def collapse(self):
        if not self.open or self.pinned:
            return
        self.open = False
        self.stack.set_visible_child_name("compact")
        self._set_live(False)
        self.anim.play()

    def toggle(self):
        if self.open:
            self.pinned = False
            self.collapse()
        else:
            self.pinned = True
            LS.set_keyboard_mode(self, LS.KeyboardMode.ON_DEMAND)
            self.expand()

    def _set_live(self, live):
        self.w_media.set_live(live)
        self.w_system.set_live(live and self.page_stack.get_visible_child_name() == "system")
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
        if name == "notifications":
            self.w_notifications.refresh()
        elif name == "calendar":
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
        self._cancel_close()
        if self.hover_opens:
            self.expand()

    def _on_leave(self, *_):
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

    def _on_click(self, gesture, n_press, x, y):
        # Un clic dans la zone compacte épingle le panneau ouvert.
        if not self.open:
            self.toggle()
            return
        if not self.pinned:
            self.pinned = True
            LS.set_keyboard_mode(self, LS.KeyboardMode.ON_DEMAND)

    def _on_key(self, _controller, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self.pinned = False
            LS.set_keyboard_mode(self, LS.KeyboardMode.NONE)
            self.collapse()
            return True
        return False

    # --- rendu ----------------------------------------------------------
    def refresh(self):
        self.w_media.refresh()
        self._refresh_compact()

    def _refresh_compact(self):
        if self.media.active:
            track = self.media.track
            self.pulse.set_visible(True)
            self.pulse.set_opacity(1.0 if self.media.playing else 0.35)
            title = track.title or ""
            self.c_title.set_text(f"{title} · {track.artist}" if track.artist else title)
            self.c_right.set_text("")
        else:
            self.pulse.set_visible(False)
            self.c_title.set_text(GLib.DateTime.new_now_local().format("%H:%M"))
            self.c_right.set_text("")

    def reload_theme(self):
        self.refresh()
