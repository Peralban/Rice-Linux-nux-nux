#!/usr/bin/env python3
"""Hyprwhale — popup Docker pour la waybar (bilingue FR / EN).

N'a pas de palette propre : il hérite de celle de GTK, que matugen
régénère à chaque changement de fond d'écran. SIGUSR1 recharge le thème.
"""

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

LANG_FILE = os.path.expanduser("~/.config/hypr/scripts/.hyprsettings-lang")
TERMINAL = "kitty"
REFRESH_MS = 3000

T = {
    "fr": {
        "title": "Docker",
        "engine_up": "Moteur actif", "engine_down": "Moteur arrêté", "engine_busy": "Redémarrage…",
        "denied": "Accès refusé", "denied_sub": "Ton compte n'est pas dans le groupe docker",
        "off_sub": "Démarre le service pour reprendre la main",
        "dashboard": "Tableau de bord", "settings": "Réglages",
        "restart_engine": "Redémarrer le moteur", "quit_engine": "Arrêter le moteur",
        "containers": "Conteneurs", "none": "Aucun conteneur",
        "none_sub": "Rien n'est encore créé sur cette machine",
        "start": "Démarrer", "stop": "Arrêter", "terminal": "Terminal",
        "s_running": "En marche", "s_stopped": "Arrêté", "s_starting": "Démarrage",
        "s_stopping": "Arrêt", "s_paused": "En pause",
        "more": "Plus",
        "events": "Événements en direct", "usage": "Ressources en direct", "prune": "Nettoyer le disque",
        "cli": "Terminal Docker", "open_dash": "Ouvrir le tableau de bord",
        "m_restart": "Redémarrer", "m_logs": "Journaux", "m_inspect": "Inspecter",
        "m_open": "Ouvrir localhost:{p}", "m_copy": "Copier l'ID", "m_copied": "ID copié",
        "m_remove": "Supprimer",
    },
    "en": {
        "title": "Docker",
        "engine_up": "Engine running", "engine_down": "Engine stopped", "engine_busy": "Restarting…",
        "denied": "Permission denied", "denied_sub": "Your account is not in the docker group",
        "off_sub": "Start the service to regain control",
        "dashboard": "Dashboard", "settings": "Settings",
        "restart_engine": "Restart engine", "quit_engine": "Stop engine",
        "containers": "Containers", "none": "No containers",
        "none_sub": "Nothing has been created on this machine yet",
        "start": "Start", "stop": "Stop", "terminal": "Terminal",
        "s_running": "Running", "s_stopped": "Stopped", "s_starting": "Starting",
        "s_stopping": "Stopping", "s_paused": "Paused",
        "more": "More",
        "events": "Live events", "usage": "Live resources", "prune": "Reclaim disk space",
        "cli": "Docker shell", "open_dash": "Open dashboard",
        "m_restart": "Restart", "m_logs": "Logs", "m_inspect": "Inspect",
        "m_open": "Open localhost:{p}", "m_copy": "Copy ID", "m_copied": "ID copied",
        "m_remove": "Remove",
    },
}

# Couleurs d'état : volontairement hors du thème. Un conteneur planté doit
# rester rouge même si l'utilisateur choisit un accent vert.
CSS = b"""
/* Fond translucide, comme le notch : la fenetre elle-meme ne dessine rien,
   c'est .hw-surface qui pose le fond. Le rayon suit celui de Hyprland
   (rounding = 10) pour que les deux coins coincident. Le flou global de
   Hyprland s'applique tout seul des que la fenetre est transparente. */
window, window.background { background: transparent; }
.hw-root .hw-surface {
  background: alpha(@window_bg_color, 0.85);
  border-radius: 10px;
}

/* meme police que la waybar : le popup parle la langue du bureau */
.hw-root, .hw-root button, .hw-root label {
  font-family: "JetBrainsMono Nerd Font Propo", "JetBrains Mono", monospace;
  font-size: 12px;
}
.hw-root .hw-logo { font-size: 15px; }
.hw-root .hw-title { font-weight: 700; font-size: 13px; }

.hw-dot { font-size: 9px; }
.hw-run  { color: #7bd88f; }
.hw-busy { color: #e8b339; }
.hw-down { color: #f2777a; }

.hw-chip {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 999px;
  background: alpha(currentColor, 0.15);
}
.hw-meta { font-size: 11px; opacity: 0.66; }
.hw-sec { font-size: 10px; letter-spacing: 1.6px; opacity: 0.65; }
.hw-count {
  font-size: 11px; padding: 1px 9px; border-radius: 999px;
  background: alpha(@accent_color, 0.20); color: @accent_color;
}
.hw-name { font-weight: 700; font-size: 12.5px; }
.hw-head { padding: 10px 12px; }
.hw-sep { background: alpha(currentColor, 0.14); min-height: 1px; }

.hw-root button.hw-item {
  min-height: 28px; padding: 0 10px;
  background: none; border: none; box-shadow: none;
}
.hw-root button.hw-item:hover { background: alpha(@accent_color, 0.14); }

.hw-root button.hw-act {
  min-height: 23px; padding: 0 10px; font-size: 11px;
  border-radius: 7px;
  background: none;
  border: 1px solid alpha(currentColor, 0.28);
  box-shadow: none;
}
.hw-root button.hw-act:hover { background: alpha(@accent_color, 0.16); }
.hw-root button.hw-act:disabled { opacity: 0.35; }
.hw-root button.hw-go { border-color: alpha(@accent_color, 0.55); color: @accent_color; }
"""


def hypr_socket():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not sig:
        return None
    path = f"/run/user/{os.getuid()}/hypr/{sig}/.socket.sock"
    return path if os.path.exists(path) else None


SOCKET = hypr_socket()


def ipc(command):
    """Parle a Hyprland en direct : ~0.2 ms, contre ~10 ms via hyprctl.
    Assez rapide pour corriger la position a chaque image d'animation."""
    if not SOCKET:
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sk:
            sk.settimeout(0.3)
            sk.connect(SOCKET)
            sk.sendall(command.encode())
            sk.recv(64)
    except OSError:
        pass


def lang():
    try:
        with open(LANG_FILE, encoding="utf-8") as fh:
            v = fh.read().strip()
            if v in T:
                return v
    except OSError:
        pass
    return "fr"


def docker(*args, timeout=20):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def spawn(*argv):
    try:
        subprocess.Popen(argv, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def host_port(ports):
    """0.0.0.0:5432->5432/tcp, [::]:… → 5432"""
    m = re.search(r":(\d+)->", ports or "")
    return m.group(1) if m else None


class Container:
    __slots__ = ("cid", "name", "image", "state", "status", "ports", "cpu", "mem", "pending")

    def __init__(self, cid, name, image, state, status, ports):
        self.cid, self.name, self.image = cid, name, image
        self.state, self.status, self.ports = state, status, ports
        self.cpu = self.mem = "—"
        self.pending = None       # "starting" / "stopping" pendant la transition


class Whale(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, default_width=380)
        self.s = T[lang()]
        self.set_title(self.s["title"])
        self.add_css_class("hw-root")

        self.engine = "unknown"
        self.containers = []
        self.pending = {}
        self.more_open = False
        self.anchor = None

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # pas de barre de titre : l'en-tete fait partie du contenu
        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.root.add_css_class("hw-surface")
        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(self.root)
        self.set_content(self.toasts)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        # se ferme quand elle perd le focus, comme un menu de barre système.
        # Le garde-fou évite de la fermer avant qu'elle l'ait jamais reçu.
        self._had_focus = False
        self._closing = None
        self.connect("notify::is-active", self._on_focus)

        self.refresh()
        GLib.timeout_add(REFRESH_MS, self._tick)
        GLib.timeout_add(700, self._remember_anchor)

    # -- en-tête -----------------------------------------------------------

    def _on_focus(self, *_):
        if self.is_active():
            self._had_focus = True
            if self._closing:                 # revenu a temps : on annule
                GLib.source_remove(self._closing)
                self._closing = None
            return
        if not self._had_focus:
            return
        # delai de grace : avec follow_mouse, un simple passage de souris
        # ne doit pas suffire a fermer le menu.
        if self._closing is None:
            self._closing = GLib.timeout_add(450, self._close_now)

    def _close_now(self):
        self._closing = None
        if not self.is_active():
            self.close()
        return GLib.SOURCE_REMOVE

    def _on_key(self, _c, keyval, _kc, _st):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return Gdk.EVENT_STOP
        return Gdk.EVENT_PROPAGATE

    # -- lecture de l'état -------------------------------------------------

    def _tick(self):
        self.refresh()
        return GLib.SOURCE_CONTINUE

    def refresh(self):
        threading.Thread(target=self._probe, daemon=True).start()

    def _probe(self):
        if shutil.which("docker") is None:
            GLib.idle_add(self._apply, "absent", [])
            return
        try:
            info = docker("info", "--format", "{{.ServerVersion}}", timeout=6)
        except (subprocess.SubprocessError, OSError):
            GLib.idle_add(self._apply, "down", [])
            return

        if info.returncode != 0:
            state = "denied" if "permission denied" in info.stderr.lower() else "down"
            GLib.idle_add(self._apply, state, [])
            return

        fmt = "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Status}}\t{{.Ports}}"
        out = docker("ps", "-a", "--format", fmt)
        items = []
        for line in out.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 6:
                items.append(Container(*parts[:6]))

        if any(c.state == "running" for c in items):
            stats = docker("stats", "--no-stream", "--format",
                           "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}", timeout=12)
            table = {}
            for line in stats.stdout.splitlines():
                p = line.split("\t")
                if len(p) >= 3:
                    table[p[0]] = (p[1], p[2].split("/")[0].strip())
            for c in items:
                if c.name in table:
                    c.cpu, c.mem = table[c.name]

        GLib.idle_add(self._apply, "up", items)

    def _apply(self, engine, items):
        self.engine = engine
        for c in items:
            if c.name in self.pending:
                want = self.pending[c.name]
                if (want == "starting" and c.state == "running") or \
                   (want == "stopping" and c.state != "running"):
                    del self.pending[c.name]
                else:
                    c.pending = want
        self.containers = items
        self._render()
        return GLib.SOURCE_REMOVE

    # -- rendu -------------------------------------------------------------

    @staticmethod
    def _sep():
        s = Gtk.Box()
        s.add_css_class("hw-sep")
        return s

    def _render(self):
        while (child := self.root.get_first_child()) is not None:
            self.root.remove(child)

        self.root.append(self._header())
        self.root.append(self._sep())
        self.root.append(self._menu())

        if self.engine != "up":
            sub = self.s["denied_sub"] if self.engine == "denied" else self.s["off_sub"]
            title = self.s["denied"] if self.engine == "denied" else self.s["engine_down"]
            self.root.append(self._sep())
            self.root.append(self._notice(title, sub))
            return

        self.root.append(self._sep())
        self.root.append(self._section_label())
        self.root.append(self._container_area())
        self.root.append(self._sep())
        self.root.append(self._more())

    def _header(self):
        box = Gtk.Box(spacing=9)
        box.add_css_class("hw-head")

        logo = Gtk.Label(label="\uf308")      # glyphe Docker de la Nerd Font
        logo.add_css_class("hw-logo")
        name = Gtk.Label(label=self.s["title"])
        name.add_css_class("hw-title")

        states = {"up": ("engine_up", "hw-run"), "busy": ("engine_busy", "hw-busy")}
        key, cls = states.get(self.engine, ("engine_down", "hw-down"))
        if self.engine == "denied":
            key = "denied"

        chip = Gtk.Box(spacing=6)
        chip.add_css_class("hw-chip")
        chip.add_css_class(cls)
        dot = Gtk.Label(label="\u25cf")
        dot.add_css_class("hw-dot")
        chip.append(dot)
        chip.append(Gtk.Label(label=self.s[key]))

        box.append(logo)
        box.append(name)
        box.append(Gtk.Box(hexpand=True))
        box.append(chip)
        return box

    def _menu(self):
        entries = [
            (self.s["dashboard"], lambda: spawn(TERMINAL, "lazydocker")),
            (self.s["settings"], lambda: spawn("xdg-open", os.path.expanduser("~/.docker"))),
            (self.s["restart_engine"], lambda: self._engine_action("restart")),
            (self.s["quit_engine"], lambda: self._engine_action("stop")),
        ]
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.set_margin_start(5); box.set_margin_end(5)
        box.set_margin_top(5); box.set_margin_bottom(5)
        for label, cb in entries:
            b = Gtk.Button(label=label)
            b.add_css_class("hw-item")
            b.get_child().set_xalign(0.0)
            b.connect("clicked", lambda _x, f=cb: f())
            box.append(b)
        return box

    def _section_label(self):
        box = Gtk.Box(spacing=8)
        box.set_margin_start(13); box.set_margin_end(11)
        box.set_margin_top(9); box.set_margin_bottom(3)
        lbl = Gtk.Label(label=self.s["containers"].upper(), xalign=0)
        lbl.add_css_class("hw-sec")
        live = sum(1 for c in self.containers if c.state == "running")
        cnt = Gtk.Label(label=f"{live} / {len(self.containers)}")
        cnt.add_css_class("hw-count")
        box.append(lbl)
        box.append(Gtk.Box(hexpand=True))
        box.append(cnt)
        return box

    def _container_area(self):
        """Seule cette zone défile : la fenêtre suit donc le contenu."""
        if not self.containers:
            return self._notice(self.s["none"], self.s["none_sub"])

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.set_margin_start(6); inner.set_margin_end(6); inner.set_margin_bottom(4)
        for c in self.containers:
            inner.append(self._row(c))

        sc = Gtk.ScrolledWindow(child=inner)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_propagate_natural_height(True)
        sc.set_max_content_height(250)
        return sc

    def _notice(self, title, subtitle):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(14); box.set_margin_end(14)
        box.set_margin_top(10); box.set_margin_bottom(12)
        t = Gtk.Label(label=title, xalign=0)
        t.add_css_class("hw-name")
        sub = Gtk.Label(label=subtitle, xalign=0)
        sub.add_css_class("hw-meta")
        sub.set_wrap(True)
        box.append(t); box.append(sub)
        return box

    def _state_of(self, c):
        if c.pending:
            return c.pending
        return {"running": "running", "paused": "paused"}.get(c.state, "stopped")

    def _row(self, c):
        st = self._state_of(c)
        cls = {"running": "hw-run", "starting": "hw-busy", "stopping": "hw-busy",
               "paused": "hw-busy"}.get(st, "hw-down")
        label = self.s.get("s_" + st, self.s["s_stopped"])

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.add_css_class("hw-card")

        top = Gtk.Box(spacing=8)
        dot = Gtk.Label(label="\u25cf"); dot.add_css_class("hw-dot"); dot.add_css_class(cls)
        name = Gtk.Label(label=c.name, xalign=0); name.add_css_class("hw-name")
        chip = Gtk.Label(label=label); chip.add_css_class("hw-chip"); chip.add_css_class(cls)
        top.append(dot); top.append(name)
        top.append(Gtk.Box(hexpand=True)); top.append(chip)

        port = host_port(c.ports)
        bits = [c.image]
        if port:
            bits.append(f"{port} \u2192 {port}")
        if c.status:
            bits.append(c.status)
        meta1 = Gtk.Label(xalign=0, label="  \u00b7  ".join(bits))
        meta1.add_css_class("hw-meta"); meta1.set_ellipsize(3)

        meta2 = Gtk.Label(xalign=0,
                          label=f"{c.cid}  \u00b7  CPU {c.cpu}  \u00b7  MEM {c.mem}")
        meta2.add_css_class("hw-meta")

        live = st == "running"
        busy = st in ("starting", "stopping")

        acts = Gtk.Box(spacing=5)
        acts.set_margin_top(4)

        toggle = Gtk.Button(label=self.s["stop"] if live else self.s["start"])
        toggle.add_css_class("hw-act")
        if not live and not busy:
            toggle.add_css_class("hw-go")
        toggle.set_sensitive(not busy)
        toggle.connect("clicked", lambda _b: self._toggle(c, live))

        term = Gtk.Button(label=self.s["terminal"])
        term.add_css_class("hw-act")
        term.set_sensitive(live)
        term.connect("clicked", lambda _b: spawn(TERMINAL, "docker", "exec", "-it", c.cid, "sh"))

        dots = Gtk.MenuButton()
        dots.set_child(Gtk.Label(label="\u22ef"))
        dots.add_css_class("hw-act")
        dots.set_always_show_arrow(False)
        dots.set_popover(self._context(c, st))

        acts.append(toggle); acts.append(term); acts.append(dots)
        for w in (top, meta1, meta2, acts):
            card.append(w)
        return card

    def _context(self, c, st):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.set_margin_top(5); box.set_margin_bottom(5)
        box.set_margin_start(5); box.set_margin_end(5)

        live = st == "running"
        port = host_port(c.ports)

        def entry(label, cb, enabled=True):
            b = Gtk.Button(label=label)
            b.add_css_class("hw-item")
            b.set_sensitive(enabled)
            b.get_child().set_xalign(0.0)
            b.connect("clicked", lambda _x: (pop.popdown(), cb()))
            box.append(b)

        entry(self.s["m_restart"], lambda: self._simple(c, "restart"), live)
        entry(self.s["m_logs"], lambda: spawn(TERMINAL, "docker", "logs", "-f", c.cid))
        entry(self.s["m_inspect"],
              lambda: spawn(TERMINAL, "sh", "-c", f"docker inspect {c.cid} | less"))
        if port:
            entry(self.s["m_open"].format(p=port),
                  lambda: spawn("xdg-open", f"http://localhost:{port}"), live)
        entry(self.s["m_copy"], lambda: self._copy(c.cid))
        entry(self.s["m_remove"], lambda: self._simple(c, "rm"), not live)

        pop.set_child(box)
        return pop

    def _more(self):
        # lazydocker n'a aucune option pour ouvrir sur un panneau precis :
        # Images / Volumes / Reseaux / Compose lanceraient tous la meme vue.
        # On ne garde donc que ce qui correspond a une commande reelle.
        # (libelle, commande, garder le terminal ouvert a la fin)
        entries = [
            (self.s["events"], "docker events", False),
            (self.s["usage"], "docker stats", False),
            (self.s["prune"], "docker system prune", True),
            (self.s["cli"], None, False),
        ]
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        inner.set_margin_start(5); inner.set_margin_end(5); inner.set_margin_bottom(5)
        for label, cmd, wait in entries:
            b = Gtk.Button(label=label)
            b.add_css_class("hw-item")
            b.get_child().set_xalign(0.0)
            b.connect("clicked", lambda _x, c=cmd, w=wait: self._run_in_term(c, w))
            inner.append(b)

        rev = Gtk.Revealer(child=inner)
        rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        rev.set_transition_duration(160)
        rev.set_reveal_child(self.more_open)

        head = Gtk.Button()
        head.add_css_class("hw-item")
        hb = Gtk.Box(spacing=8)
        chev = Gtk.Label(label="\u25be" if self.more_open else "\u25b8")
        hb.append(chev)
        hb.append(Gtk.Label(label=self.s["more"]))
        head.set_child(hb)

        def toggle(_b):
            self.more_open = not self.more_open
            rev.set_reveal_child(self.more_open)
            chev.set_label("\u25be" if self.more_open else "\u25b8")
            if self.more_open:
                self._hold_anchor(420)
            else:
                self._hold_anchor(500, follow=True)
        head.connect("clicked", toggle)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_margin_start(5); box.set_margin_end(5)
        box.set_margin_top(4); box.set_margin_bottom(5)
        box.append(head)
        box.append(rev)
        return box

    # -- actions -----------------------------------------------------------

    def _toggle(self, c, live):
        self.pending[c.name] = "stopping" if live else "starting"
        c.pending = self.pending[c.name]
        self._render()
        self._run_async("stop" if live else "start", c.cid)

    def _simple(self, c, verb):
        if verb == "restart":
            self.pending[c.name] = "starting"
            c.pending = "starting"
            self._render()
        self._run_async(verb, c.cid)

    def _run_async(self, verb, cid):
        def work():
            try:
                docker(verb, cid, timeout=30)
            except (subprocess.SubprocessError, OSError):
                pass
            GLib.idle_add(self.refresh)
        threading.Thread(target=work, daemon=True).start()

    def _engine_action(self, verb):
        units = ["docker.socket", "docker.service"] if verb == "restart" else ["docker.socket"]
        self.engine = "busy"
        self._render()
        spawn("pkexec", "systemctl", verb, *units)
        GLib.timeout_add(3500, lambda: (self.refresh(), GLib.SOURCE_REMOVE)[1])

    def _remember_anchor(self):
        """La windowrule pose la fenêtre ; on retient ce coin haut-gauche."""
        try:
            out = subprocess.run(["hyprctl", "clients", "-j"],
                                 capture_output=True, text=True, timeout=3)
            for c in json.loads(out.stdout or "[]"):
                if c.get("class") == "dev.local.HyprWhale":
                    self.anchor = tuple(c["at"])
                    break
        except (subprocess.SubprocessError, OSError, ValueError):
            pass
        return GLib.SOURCE_REMOVE

    def _reanchor(self):
        """Hyprland agrandit les fenêtres flottantes autour de leur centre.
        On recolle le coin haut-gauche a chaque image plutot qu'une fois a
        la fin : sinon la fenetre monte pendant l'animation puis redescend
        d'un coup, ce qui se voit."""
        if not self.anchor:
            return GLib.SOURCE_REMOVE
        ipc(f"/dispatch movewindowpixel exact {self.anchor[0]} {self.anchor[1]},"
            f"class:dev.local.HyprWhale")
        return GLib.SOURCE_REMOVE

    def _hold_anchor(self, duration_ms=420, follow=False):
        """Suit la transition image par image.

        `follow` ajoute une demande de retaille : GTK ne rétrécit jamais de
        lui-même, donc au repli on lui redemande son minimum a chaque image.
        Il epouse alors la hauteur du contenu qui se replie, au lieu de
        rester grand puis de sauter a la fin."""
        if not self.anchor:
            return
        self._hold_until = duration_ms
        width = self.get_width()

        def frame():
            if follow:
                # hauteur que GTK veut pour le contenu a cet instant : elle
                # decroit pendant le repli, la fenetre suit donc l'animation.
                _, natural, _, _ = self.measure(Gtk.Orientation.VERTICAL, width)
                ipc(f"/dispatch resizewindowpixel exact {width} {natural},"
                    f"class:dev.local.HyprWhale")
            self._reanchor()
            self._hold_until -= 16
            return self._hold_until > 0
        GLib.timeout_add(16, frame)

    def _run_in_term(self, command, wait):
        """command a None : simple shell. wait : garder la fenetre ouverte
        quand la commande se termine (prune rend la main, pas `docker events`)."""
        if command is None:
            spawn(TERMINAL)
        elif wait:
            spawn(TERMINAL, "sh", "-c", f"{command}; printf '\n[terminé] '; read _")
        else:
            spawn(TERMINAL, "sh", "-c", command)

    def _shrink(self):
        """Rappel : GTK agrandit une fenêtre mappée mais ne la rétrécit
        jamais. On lui redemande son minimum, qu'il calcule sur le contenu."""
        self._hold_anchor(300, follow=True)
        return GLib.SOURCE_REMOVE

    def _copy(self, cid):
        Gdk.Display.get_default().get_clipboard().set(cid)
        self.toasts.add_toast(Adw.Toast(title=self.s["m_copied"], timeout=2))

    def reload_theme(self):
        """Appelé sur SIGUSR1, quand matugen a régénéré la palette."""
        Gtk.Settings.get_default().reset_property("gtk-theme-name")
        self._render()


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="dev.local.HyprWhale")

    def do_activate(self):
        win = self.props.active_window or Whale(self)
        win.present()
        signal.signal(signal.SIGUSR1, lambda *_: GLib.idle_add(win.reload_theme))


if __name__ == "__main__":
    App().run(None)
