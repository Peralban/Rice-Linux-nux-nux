# rice-repo

A Hyprland setup on Arch Linux, built on top of the
[JaKooLit](https://github.com/JaKooLit/Hyprland-Dots) dotfiles and extended with
five custom GTK4 applications.

One rule governs the whole repository: **no colour is ever hardcoded.** The
wallpaper decides the palette, and everything else follows automatically — bar,
panels, launcher, terminal, notifications, login screen.

---

## The four applications

Written in Python + GTK4 / libadwaita, bilingual French / English with a language
switcher, and themed from the system palette.

| | Shortcut | What it does |
|---|---|---|
| **HyprSettings** | `Super + Shift + K` | Settings panel: spacing, decoration, blur, bar, mouse and keyboard |
| **HyprKeys** | `Super + Shift + /` | Graphical keybinding editor — captures the key combination as you press it |
| **HyprWhale** | click the whale | Docker menu: containers, start/stop, terminal, logs |
| **HyprNotch** | `Super + N`, or hover | Dynamic notch: media, calendar, system, file shelf |
| **CheatSheet** | `Super + /` | Filterable shortcut list in rofi |

### HyprSettings

Every slider applies **live** through `hyprctl keyword`; nothing touches disk
until you press *Save*. It writes to four different files depending on the
setting — `looknfeel.conf`, `input.conf`, the waybar config and its stylesheet —
changing only the value concerned.

### HyprKeys

Reads and rewrites `keybinds.conf` while preserving comments, ordering and
formatting. The combination button captures the keys you actually press and
translates them into Hyprland syntax (`$mainMod SHIFT, S`).

### HyprNotch

A notch living **inside the bar**, in the spirit of BoringNotch. It takes the
place waybar's `mpris` module used to occupy: compact it shows the current
track, on hover it expands downward into a panel — cover art, progress,
controls, then a right column that switches between calendar, system stats and
a file shelf.

The compact pill deliberately mirrors the `mpris` module it replaced — the same
Nerd Font player glyph, the same italic `artist title` — and it sizes itself to
its text instead of holding a fixed width, so it reads as one of the bar's own
islands.

The pill shows the **album art** when the player publishes one, and falls back
to the player's Nerd Font glyph when it doesn't.

It also **takes its geometry from the bar**. Font, weight, size, corner radius
and horizontal padding are read out of `islands.css`; the height and vertical
position are measured on waybar's own layer surface through the Hyprland
socket. Move a slider in HyprSettings and the notch follows within a second —
there is no second set of values to keep in sync.

With nothing playing it draws nothing at all, but the surface stays there, so
hovering the middle of the bar still opens it.

The file shelf is a drop target. Files dropped on it are never copied or moved:
it keeps paths, and each row is itself a drag source, so you pick them back up
wherever you need them.

It is a **layer surface**, not a floating window, which is what makes it centre
itself and expand from the middle for free. Media comes from **MPRIS through
Playerctl signals**, so it follows whichever player is active — Spotify,
Firefox, VLC — and nothing is hardcoded. Only the playback position is polled,
and only while the panel is open.

### HyprWhale

Refreshes every 3 seconds in a background thread. State colours (green / amber /
red) are **deliberately excluded** from the theme: a crashed container has to
stay red even under a green accent.

The `⋯` context menu adapts to state — *Remove* is greyed out on a running
container, *Open localhost:port* on a stopped one.

---

## The reactive theme

`Super + W` opens the wallpaper picker. Once an image is chosen,
[matugen](https://github.com/InioX/matugen) extracts a Material You palette from
it, regenerates **twelve files**, then notifies every application concerned:

| Target | Generated file | Signal sent |
|---|---|---|
| waybar | `waybar/colors.css` | `pkill -SIGUSR2 waybar` |
| hyprland | `hypr/colors.conf` | `hyprctl reload` |
| kitty | `kitty/colors.conf` | `kill -SIGUSR1 $(pidof kitty)` |
| GTK 3 and 4 | `gtk-*/colors.css` | `pkill -SIGUSR1 -f HyprWhale.py` |
| vicinae | `themes/matugen.toml` | `vicinae theme set matugen` |
| hyprnotch | reads `waybar/colors.css` | file monitor, live |
| rofi, cava, spicetify, vesktop | — | — |

GTK applications inherit the palette because `gtk-3.0/gtk.css` and
`gtk-4.0/gtk.css` import the `colors.css` matugen writes. **Without those two
one-line files, matugen generates the colours but GTK never reads them** — the
quietest trap in this whole configuration.

---

## Shortcuts

### Windows

| | |
|---|---|
| `Super + Q` | Close |
| `Super + Shift + Q` | Kill the process |
| `Super + Space` | Floating ↔ tiled |
| `Super + Shift + F` | Fullscreen |
| `Super + J` | Toggle split direction |
| `Super + S` | Show / hide the scratchpad |
| `Super + Alt + S` | Send the window to the scratchpad |
| `Super + ← ↑ ↓ →` | Move focus |
| `Super + Ctrl + ← ↑ ↓ →` | Move the window |
| `Super + Shift + ← ↑ ↓ →` | Resize |

The scratchpad is how you hide a window without closing it — Spotify quits on
`Super + Q` despite having a tray icon, so `Super + Alt + S` is the way to keep
music playing.

### Applications

| | |
|---|---|
| `Alt + Space` | Vicinae launcher |
| `Super + Enter` | Terminal |
| `Super + Shift + Enter` | Floating terminal |
| `Super + E` | Thunar |
| `Super + Shift + E` | Yazi |
| `Super + B` | Browser |
| `Super + C` | Colour picker |
| `Super + N` | Open / close the notch |
| `Super + Shift + S` | Screenshot — saved **and** copied to the clipboard |
| `Super + L` | Lock |
| `Ctrl + Alt + Delete` | Quit Hyprland |

### Appearance

| | |
|---|---|
| `Super + W` | Wallpaper + palette regeneration |
| `Super + Ctrl + B` | Waybar style |
| `Super + Alt + B` | Waybar layout |
| `Super + R` | Restart waybar and swaync |
| `Super + H` | Hide the bar |

### Workspaces

`Super + 1…0` to switch, `Super + Shift + 1…0` to send the window there,
`Super + scroll` to cycle, three fingers horizontally on the touchpad.

---

## Dependencies

```bash
sudo pacman -S --needed \
  hyprland waybar rofi kitty swaync hyprlock hypridle hyprpolkitagent \
  awww matugen-bin thunar yazi \
  gnome-keyring seahorse \
  brightnessctl hyprpicker playerctl wl-clipboard grim slurp \
  blueman network-manager-applet pavucontrol nwg-displays mission-center \
  docker docker-compose docker-buildx lazydocker \
  python-gobject gtk4 libadwaita gtk4-layer-shell \
  ttf-jetbrains-mono-nerd noto-fonts-emoji fastfetch btop
```

```bash
yay -S vicinae-bin sddm-silent-theme
```

Docker needs two more steps:

```bash
sudo systemctl enable --now docker.socket
sudo usermod -aG docker $USER
```

Then **reboot**. Logging out is not enough: `user@1000.service` survives the end
of a session and keeps the group set it started with.

---

## Installation

```bash
git clone git@github.com:Peralban/Rice-Linux-nux-nux.git ~/.rice-repo
cd ~/.rice-repo && ./install.sh
```

`install.sh` symlinks every file in the repository into `~/.config`, moving
whatever it replaces to `~/.config-backup-<date>`.

Files are **never copied**: `~/.config/hypr/hyprland.conf` is a symlink to
`~/.rice-repo/config/hypr/hyprland.conf`. Editing either one is the same thing,
and `git status` sees the change immediately.

The login screen lives outside `$HOME` and needs root, so it has its own script:

```bash
~/.rice-repo/system/sddm/install-sddm.sh
```

---

## Structure

```
config/
├── hypr/
│   ├── hyprland.conf          autostart, monitor, sources
│   ├── hyprland.lua           the 0.57 port — validated, see Notes
│   ├── configs/               keybinds, windowrules, tags, looknfeel, input, animations
│   ├── scripts/               the applications + screenshot, wallpaper picker
│   └── scripts/hyprnotch/     the notch, split into core / theme / ui / widgets
├── waybar/
│   ├── UserModules            Docker module and brightness slider
│   ├── Modules                base definitions (tray, mpris, backlight…)
│   ├── configs/               bar layouts
│   └── style/                 stylesheets
├── matugen/                   palette generation chain
├── swaync/themes/             notification centre
├── vicinae/                   launcher settings (theme, compact mode, telemetry)
└── gtk-3.0, gtk-4.0/          the two lines that wire GTK into matugen

system/
└── sddm/                      login screen, mirrors the lock screen
```

---

## Notes

A few traps hit while building this, kept here because they are written nowhere
else.

**Hyprland 0.56 changed the window rule syntax.** `class:^(kitty)$` becomes
`match:class ^(kitty)$`, `float` becomes `float true`, `ignorealpha` becomes
`ignore_alpha`, and `ignorezero` no longer exists. The `.conf` format itself
disappears in 0.57 in favour of Lua.

**The `swww` package was renamed `awww`.** Configurations still calling
`swww-daemon` fail silently.

**matugen 4.x** refuses to pick between candidate source colours without an
interactive terminal: `--prefer saturation` is mandatory from a keybinding. It
also dropped `arguments = [...]` in `[config.wallpaper]` in favour of a single
command containing `{{ image }}`.

**Hyprland grows floating windows around their centre.** A popup that expands
therefore climbs off the top of the screen. HyprWhale re-anchors its top-left
corner on every frame, through the IPC socket (0.16 ms) rather than `hyprctl`
(10 ms).

**GTK grows a mapped window but never shrinks it.** `set_default_size` has no
effect once the window is shown; you have to ask the compositor to resize using
the height `measure()` reports.

**Nerd Font glyphs live in the Unicode private use area.** A stray space after a
glyph (`" "`) visibly shifts the icon inside its pill.

**SDDM 0.21 runs a Qt6 greeter.** A theme must declare `QtVersion=6` in its
`metadata.desktop` or it is ignored in silence and SDDM falls back to a plain
white box. The three stock themes (elarun, maldives, maya) are all Qt5 and never
load.

**The `sddm` user cannot read `$HOME`** when it is `drwx------`. The login
screen wallpaper has to be copied into the theme directory, not symlinked.

**zsh-autocomplete must be sourced before oh-my-zsh.** oh-my-zsh runs `compinit`
before sourcing plugins, so the plugin's `Completions/` directory reaches
`fpath` after the scan and its functions are never registered.

**Vicinae's compact mode does nothing while something is showing at root.** An
unread "What's New" item keeps the launcher expanded, and the telemetry notice
only stops counting as one when `telemetry.system_info` is set to `false`. The
file-indexer toast does the same for the first few seconds after a server
restart. The window never changes size either way — the layer surface stays
770x480 and only the drawn content collapses — so `hyprctl layers` cannot tell
you whether compact mode is on. Take a screenshot.

**Vicinae writes its config in place, following symlinks**, so `settings.json`
can live in the repository like everything else. Changing a setting in its GUI
edits the repository file directly.

**A GTK4 window grows but never shrinks itself.** Lowering a size request does
nothing once the window is mapped; only `set_default_size()` with explicit
values brings a layer surface back down. HyprNotch's whole open/close animation
rests on that one call.

**`Gdk.Surface.set_input_region()` is overwritten by GTK on Wayland.** The
obvious notch design — one big transparent surface with a clickable hole — is
therefore impossible: the region is computed correctly and then ignored, and
the transparent area keeps swallowing clicks. The surface has to be exactly the
size of what you can see, which is also what makes hover detection reliable.

**A `Gtk.Stack` is homogeneous by default**, so its minimum size is that of its
largest page. The compact view was being centred inside the expanded view's
224 px and drawn outside the 30 px window — visible as an empty pill.
`hhomogeneous=False, vhomogeneous=False` is the fix.

**gtk4-layer-shell must be loaded before libwayland-client.** From Python it
never is, so the launcher re-executes itself once with `LD_PRELOAD` set;
without it the window silently falls back to a normal toplevel.

**A fully transparent GTK window never commits a frame.** With nothing playing,
the notch's shell draws nothing — and the layer surface stayed frozen at GTK's
200x200 fallback, an invisible block in the middle of the bar. GTK's own idea of
the window was already correct (230x22); it simply never told the compositor.
One per cent of background alpha is enough to force the frame, and measured
against a bare bar the difference is 1/255.

**The bar's centre is deliberately empty.** `modules-center` holds nothing:
HyprNotch sits there as a layer surface with `exclusive_zone = -1`, which is
what lets it ignore waybar's own exclusive zone and share the same strip. The
clock's hover calendar is off for the same reason — the notch has one.

**An ellipsizing `Gtk.Label` reports a truncated natural width**, so measuring
the pill through `measure()` made it size to the cut-off text and then cut the
text to fit. `create_pango_layout()` gives the real extent. A `Gtk.Picture` has
the opposite problem: its natural size is the texture's, so the album art grew
or shrank with the length of the track title until it was clipped by a
non-propagating container.

**Nothing in the panel pins it open.** An earlier version pinned on any click,
which meant clicking a tab left the notch stuck open with no obvious way back —
only `Super + N` closes a pinned panel, and hovering away no longer worked.
Hover opens and closes; `Super + N` is the only thing that pins.

**Measure the bar, don't recompute it.** Deriving the pill's height from the
font size and padding gave 25 px where waybar's islands were 23. Asking the
compositor for waybar's layer geometry and subtracting the group padding is
exact, and it keeps working when any of those settings change.

**Nerd Font player logos are not icon-sized.** The Spotify glyph fills far more
of its em box than the bar's own icons: at the same font size it rendered 12 px
tall against their 9.5. The pill scales its glyph to 78 % so the two match, and
takes `@secondary` — the colour waybar gives every module — instead of the
accent.

**waybar's `font-size: 94%` is not 94%.** It sits on the universal selector, so
it re-applies at every level of waybar's widget tree and the text it actually
draws is far smaller than the figure suggests. Reproducing the percentage
literally gave a pill a third too large — capital letters 10.5 px against the
bar's 8.0. HyprNotch scales the percentage by a factor measured between the two
renders rather than trusting the number.

**A drop target for files needs more than `GdkFileList`.** File managers offer
one, but browsers and Electron apps hand over `text/uri-list` or a bare path as
text. HyprNotch's target accepts all three and normalises them to paths. It also
opens the panel in a single resize during a drag rather than animating twenty of
them under a pointer the compositor is already tracking.

Drag-and-drop events are traced to `~/.cache/hyprnotch/dnd.log` — the file only
grows when something is dropped, and it records what the source actually
offered.

**`Gdk.ContentProvider.new_typed()` does not exist in the Python bindings.** It
is a C varargs convenience, so calling it from a `prepare` handler raised
inside the signal and no drag ever started — dropping files *into* the shelf
worked, dragging them back out silently did nothing. Build the provider from
`GObject.Value` instead, and union a `GdkFileList`, a `GFile` and a raw
`text/uri-list` so any target finds a format it understands.

**Turning the shell transparent before the animation ends looks broken.** When
the notch collapses back to nothing, dropping the background immediately left
the panel's text floating over the desktop for the last frames of the shrink.
The ghost state is applied on the animation's `done` signal instead, and fades
out over 140 ms.

**The shell's 1 px border eats into the pill.** Asking the compact box for the
full island height left it a pixel taller than the space inside the border, so
everything in it — the album art most visibly — sat a pixel low. The box asks
for the height minus the border on both sides.
