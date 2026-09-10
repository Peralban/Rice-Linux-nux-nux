# rice-repo

A Hyprland setup on Arch Linux, built on top of the
[JaKooLit](https://github.com/JaKooLit/Hyprland-Dots) dotfiles and extended with
four custom GTK4 applications.

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
  python-gobject gtk4 libadwaita \
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
│   └── scripts/               the four applications + screenshot, wallpaper picker
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
