# Rice

A Hyprland desktop on Arch Linux, grown out of the
[JaKooLit](https://github.com/JaKooLit/Hyprland-Dots) dotfiles and rebuilt
around five hand-written GTK4 applications.

One rule governs the whole repository: **no colour is ever written by hand.**
The wallpaper decides the palette, and fourteen surfaces follow it — the bar,
the notch, the terminal, the file manager, the browser chrome, the PDF reader,
the system monitor, the launcher, the notifications, Spotify, Discord, the
window borders and the login screen.

---

## What it looks like

![The bar](docs/screens/waybar.png)

The notch lives inside the bar and expands downward on hover:

![The notch, calendar page](docs/screens/notch-calendar.png)

Its AirDrop page, which drives [airdrop-mt7921](https://github.com/jedbillyb/airdrop-mt7921):

![The notch, AirDrop page](docs/screens/notch-airdrop.png)

The Docker menu:

![HyprWhale](docs/screens/hyprwhale.png)

Nothing above uses a fixed colour. Every state below is the same palette,
derived from the current wallpaper — `primary` for visible, `tertiary` for a
transition, `error` for a fault:

![AirDrop states](docs/screens/airdrop-states.png)

---

## The palette

`Super + W` opens the wallpaper picker. Once an image is chosen,
[matugen](https://github.com/InioX/matugen) extracts a Material You palette from
it, regenerates one file per target, and tells each one to look again.

| Target | Generated file | How it hears about it |
|---|---|---|
| waybar | `waybar/colors.css` | `pkill -SIGUSR2 waybar` |
| hyprland | `hypr/colors.conf` | `hyprctl reload` |
| hyprlock | reads `hypr/colors.conf` | sourced at launch |
| kitty | `kitty/colors.conf` | `kill -SIGUSR1 $(pidof kitty)` |
| GTK 4 | `gtk-4.0/colors.css` | `pkill -SIGUSR1 -f "Hypr(Whale\|Notes)[.]py"` |
| GTK 3 | `gtk-3.0/colors.css` | `gtk3-reload.sh` — restart, see Notes |
| hyprnotch | reads `waybar/colors.css` | file monitor, live |
| swaync | imports `waybar/colors.css` | `swaync-client -rs` |
| rofi | `rofi/colors.rasi` | imported at launch |
| zathura | `zathura/colors.rc` | none — every launch is a fresh process |
| btop | `btop/themes/matugen.theme` | none — same |
| vicinae | `themes/matugen.toml` | `vicinae theme set matugen` |
| spicetify | `spicetify/.../color.ini` | `spicetify apply -n` |
| vesktop | `vesktop/themes/matugen.css` | read live |
| cava | its whole config | `pkill -USR1 cava` |

Three of those needed more than a generated file, and each for its own reason.

**GTK 4 applications** inherit the palette because `gtk-4.0/gtk.css` imports the
`colors.css` matugen writes. That one-line file is the quietest trap in this
configuration: without it the colours are generated and never read.

**GTK 3 applications** — Thunar, seahorse, the network editor — need a theme
that actually consumes the colour names. `adw-gtk-theme` is libadwaita ported
to GTK 3 and references `@window_bg_color` 219 times, so overriding that name
in the user stylesheet recolours all of it. Select it once; this desktop has no
XSettings daemon and GTK 3 reads GSettings here, not `settings.ini`:

```bash
gsettings set org.gnome.desktop.interface gtk-theme adw-gtk3-dark
```

**Helium**, the browser, is a Chromium fork. It has no palette of its own worth
driving, but it does have the Linux GTK backend — set its appearance to GTK in
`chrome://settings/appearance` and it rides on the GTK 3 work above. The key it
writes is `extensions.theme.system_theme`, not the `browser.theme` family.

---

## The five applications

Python + GTK4 / libadwaita, bilingual French / English with a language
switcher, themed from the system palette.

| | Shortcut | What it does |
|---|---|---|
| **HyprSettings** | `Super + Shift + K` | Spacing, decoration, blur, bar, notch, mouse and keyboard |
| **HyprKeys** | `Super + Shift + /` | Keybinding editor — captures the combination as you press it |
| **HyprWhale** | click the whale | Docker: containers, start/stop, terminal, logs |
| **HyprNotch** | `Super + Shift + N`, or hover | Media, calendar, system, file shelf, AirDrop, pinned note |
| **HyprNotes** | `Super + N` | Notes as plain text files, sidebar at the screen edge |
| **CheatSheet** | `Super + /` | Filterable shortcut list in rofi |

### HyprSettings

Every slider applies **live** — through `hyprctl keyword` under the `.conf`
parser, through `hyprctl eval hl.config({...})` under the Lua one, which
refuses `keyword` outright. Nothing touches disk until you press *Save*. It
writes to five different files depending on the setting — `looknfeel.conf`,
`input.conf`, the waybar config and its stylesheet, and the notch's JSON —
changing only the value concerned.

### HyprKeys

Reads and rewrites `keybinds.conf` while preserving comments, ordering and
formatting. The combination button captures the keys you actually press and
translates them into Hyprland syntax (`$mainMod SHIFT, S`).

### HyprNotch

A notch living **inside the bar**, in the spirit of BoringNotch. It takes the
place waybar's `mpris` module used to occupy: compact it shows the current
track, on hover it expands downward into a panel — cover art, progress,
controls, then a right column that switches between calendar, system stats, a
file shelf, AirDrop and the note you pinned.

The file shelf is a drop target. Files dropped on it are never copied or moved:
it keeps paths, and each row is itself a drag source, so you pick them back up
wherever you need them. Image, PDF and video rows carry a thumbnail — the
desktop's own when it is still valid, otherwise one requested from tumbler over
D-Bus. The themed icon stays as placeholder and fallback.

It is a **layer surface**, not a floating window, which is what makes it centre
itself and expand from the middle for free. Media comes from **MPRIS through
Playerctl signals**, so it follows whichever player is active.

### HyprNotes

One `.md` file per note in `~/.local/share/hyprnotes/`. No database, no custom
format: the notes stay greppable, editable in `nvim`, and **they outlive the
app**. The sidebar floats over the text rather than pushing it, and opens three
ways — mouse at the left edge, `Ctrl + B`, or the header button.

The text stays plain, but three conventions get dressed up in place: `# Heading`
down to `###`, `**bold**`, and `- [ ]` / `- [x]` checkboxes ticked by clicking
the marker. The markers stay visible, only dimmed — hiding them inside an
editable area makes the cursor jump across characters you cannot see.

**The folder is also the bus between the app and the notch.** Both watch it with
`Gio.FileMonitor`, so ticking a box in the notch moves a file and the window
follows, and the other way round. No daemon, no socket. Each note carries two
independent pins: one keeps it at the top of the list, the other shows it in the
notch, and only one note at a time can hold the second.

Also published on its own, so it runs without the rest of this rice:
**[Peralban/HyprNotes](https://github.com/Peralban/HyprNotes)**. The copy here is
the one this configuration symlinks; the notch tab lives in that repository
under `integrations/hyprnotch/`, and points back here for the other half.

### HyprWhale

Refreshes every 3 seconds in a background thread. State colours (green / amber /
red) are **deliberately excluded** from the theme: a crashed container has to
stay red even under a green accent.

The `⋯` context menu adapts to state — *Remove* is greyed out on a running
container, *Open localhost:port* on a stopped one.

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
| `Super + D` | Discord |
| `Super + C` | Colour picker |
| `Super + N` | Open / hide the notes |
| `Super + Shift + N` | Open / close the notch |
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

## Installation

```bash
git clone git@github.com:Peralban/Rice-Linux-nux-nux.git ~/.rice-repo
cd ~/.rice-repo && ./install.sh
```

That installs everything. Components can also be taken one at a time — the bar
without the launcher, the notch without the login screen:

```bash
./install.sh --list             # what is available
./install.sh waybar matugen     # just those
./install.sh --dry-run          # show the links, touch nothing
```

`install.sh` symlinks the files into `~/.config`, moving whatever it replaces to
`~/.config-backup-<date>`. It tells you when a component will look broken
without its neighbour — the bar without `matugen` has no palette to read.

Files are **never copied**: `~/.config/hypr/hyprland.conf` is a symlink to
`~/.rice-repo/config/hypr/hyprland.conf`. Editing either one is the same thing,
and `git status` sees the change immediately.

### Dependencies

```bash
sudo pacman -S --needed \
  hyprland waybar rofi kitty swaync hyprlock hypridle hyprpolkitagent \
  awww matugen-bin thunar yazi adw-gtk-theme zathura zathura-pdf-mupdf \
  gnome-keyring seahorse \
  brightnessctl pamixer hyprpicker playerctl wl-clipboard grim slurp \
  blueman network-manager-applet pavucontrol nwg-displays mission-center \
  tumbler poppler-glib ffmpegthumbnailer libgsf libgepub libopenraw \
  docker docker-compose docker-buildx lazydocker \
  python-gobject gtk4 libadwaita gtk4-layer-shell \
  ttf-jetbrains-mono-nerd noto-fonts-emoji fastfetch btop
```

```bash
yay -S vicinae-bin sddm-silent-theme
```

Optional, and only if you want those two themed: `vesktop` replaces the
official Discord client, which accepts no CSS at all, and `spicetify-cli`
patches Spotify. Both have a generated theme waiting for them in this
repository; without the client, the file is written to a folder nothing reads.

### The steps install.sh cannot do

Symlinking is all `install.sh` does. These change system or session state, so
they are yours to run:

```bash
# GTK 3 applications, including Thunar
gsettings set org.gnome.desktop.interface gtk-theme adw-gtk3-dark

# Docker
sudo systemctl enable --now docker.socket
sudo usermod -aG docker $USER

# Spotify, once
spicetify backup apply

# The login screen: outside $HOME, needs root
~/.rice-repo/system/sddm/install-sddm.sh
```

In Vesktop, enable `matugen.css` under **Settings → Themes**. In Helium, set the
appearance to GTK in `chrome://settings/appearance`.

---

## Structure

```
config/
├── hypr/
│   ├── hyprland.conf          autostart, monitor, sources
│   ├── hyprland.lua           the 0.57 port — reads the .conf files, see Notes
│   ├── configs/               keybinds, windowrules, tags, looknfeel, input, animations
│   ├── scripts/               volume, brightness, lock, screenshot, wallpaper picker
│   ├── scripts/hyprnotch/     the notch, split into core / theme / ui / widgets
│   └── scripts/hyprnotes/     the notes: store, light markup, window
├── waybar/
│   ├── UserModules            Docker module and brightness slider
│   ├── Modules                base definitions (tray, mpris, backlight…)
│   ├── configs/               bar layouts
│   └── style/                 stylesheets
├── matugen/
│   ├── config.toml            every target and its post hook
│   └── templates/             one template per target
├── swaync/                    notification centre — style.css does the imports
├── zathura/                   PDF reader, colours included from colors.rc
├── btop/                      system monitor, color_theme points at the generated one
├── vicinae/                   launcher settings (theme, compact mode, telemetry)
├── airdrop/                   AirDrop: patches, tools, recovery path — see its README
└── gtk-3.0, gtk-4.0/          the two lines that wire GTK into matugen

docs/screens/                  the screenshots above

system/
└── sddm/                      login screen, mirrors the lock screen
```

---

## Notes

Traps hit while building this, kept because they are written nowhere else.
Grouped by where they bite.

### Hyprland and Wayland

**Hyprland 0.56 changed the window rule syntax.** `class:^(kitty)$` becomes
`match:class ^(kitty)$`, `float` becomes `float true`, `ignorealpha` becomes
`ignore_alpha`, and `ignorezero` no longer exists. The `.conf` format itself
disappears in 0.57 in favour of Lua.

**Under the Lua config, `hyprctl keyword` is refused outright** — *"keyword
can't work with non-legacy parsers. Use eval."* That is the one mechanism
HyprSettings uses to apply a slider live, so every control went silent the day
`hyprland.lua` landed in `~/.config/hypr/`. The panel now detects the parser and
falls back to `hyprctl eval hl.config({...})`.

**`hyprland.lua` reads `looknfeel.conf` and `input.conf` rather than freezing
its own values**, the same way it already reads `colors.conf` for the palette.
Without that, it overwrote every setting at each start and the panel appeared to
forget what you had saved.

**A `css_gap` wants its four sides named.** `gaps_out = { 2, 3, 3, 3 }` is
accepted without a word of complaint and then ignored, which silently leaves the
outer gaps at zero. Only `{ top = …, right = …, bottom = …, left = … }` — or a
single integer — actually lands.

**Hyprland grows floating windows around their centre.** A popup that expands
therefore climbs off the top of the screen. HyprWhale re-anchors its top-left
corner on every frame, through the IPC socket (0.16 ms) rather than `hyprctl`
(10 ms).

**gtk4-layer-shell must be loaded before libwayland-client.** From Python it
never is, so the launcher re-executes itself once with `LD_PRELOAD` set;
without it the window silently falls back to a normal toplevel.

**`Gdk.Surface.set_input_region()` is overwritten by GTK on Wayland.** The
obvious notch design — one big transparent surface with a clickable hole — is
therefore impossible: the region is computed correctly and then ignored, and
the transparent area keeps swallowing clicks. The surface has to be exactly the
size of what you can see, which is also what makes hover detection reliable.

**`ON_DEMAND` does not mean "take the keyboard", it means "the compositor will
hand it over on the next click".** Switching to it *during* a click is therefore
too late: that click was already settled under the previous mode, and a second
one was needed for nothing. Arm it on hover instead — measured safe, since
switching an already-mapped surface to `ON_DEMAND` takes no focus on its own. A
surface *mapped* with it does, which is the case that misleads you.

**A layer surface in `ON_DEMAND` keeps the keyboard only until you click
elsewhere.** The compositor then serves the next window, but the notch stays
pinned and open — alive on screen, listening to nothing. It has to watch
`notify::is-active`, save, release the keyboard and unpin on its own.

### GTK

**A GTK window grows but never shrinks itself.** Lowering a size request does
nothing once the window is mapped: only `set_default_size()` with explicit
values brings a layer surface back down, and the value to give it is the height
`measure()` reports rather than one you compute. HyprNotch's whole open/close
animation rests on that one call.

**A `Gtk.Stack` is homogeneous by default**, so its minimum size is that of its
largest page. The compact view was being centred inside the expanded view's
224 px and drawn outside the 30 px window — visible as an empty pill.
`hhomogeneous=False, vhomogeneous=False` is the fix.

**A fully transparent GTK window never commits a frame.** With nothing playing,
the notch's shell draws nothing — and the layer surface stayed frozen at GTK's
200x200 fallback, an invisible block in the middle of the bar. GTK's own idea of
the window was already correct (230x22); it simply never told the compositor.
One per cent of background alpha is enough to force the frame, and measured
against a bare bar the difference is 1/255.

**An empty label still reserves its line.** Two of them, one under the AirDrop
controls and one inside its hero, held the whole panel off the bottom of its
column and pushed the logo away from the rule. Visibility has to follow the
text, or the layout answers to strings nobody can see.

**An ellipsizing `Gtk.Label` reports a truncated natural width**, so measuring
the pill through `measure()` made it size to the cut-off text and then cut the
text to fit. `create_pango_layout()` gives the real extent. A `Gtk.Picture` has
the opposite problem: its natural size is the texture's, so the album art grew
or shrank with the length of the track title until it was clipped by a
non-propagating container.

**A drop target for files needs more than `GdkFileList`.** File managers offer
one, but browsers and Electron apps hand over `text/uri-list` or a bare path as
text. HyprNotch's target accepts all three and normalises them to paths. It also
opens the panel in a single resize during a drag rather than animating twenty of
them under a pointer the compositor is already tracking. Events are traced to
`~/.cache/hyprnotch/dnd.log`, which only grows when something is dropped.

**`Gdk.ContentProvider.new_typed()` does not exist in the Python bindings.** It
is a C varargs convenience, so calling it from a `prepare` handler raised inside
the signal and no drag ever started — dropping files *into* the shelf worked,
dragging them back out silently did nothing. Build the provider from
`GObject.Value` instead, and union a `GdkFileList`, a `GFile` and a raw
`text/uri-list` so any target finds a format it understands.

**GTK resolves a relative `@import` from the file it is reading**, which for a
symlinked stylesheet is the link, not its target. That is what lets
`swaync/style.css` live in this repository and still reach
`../../.config/waybar/colors.css` once it is linked into place.

### Theming

**A GTK 3 theme does not read libadwaita's colour names.** Adwaita 3.24
consumes `@theme_bg_color`, `@theme_base_color` and that family; pointing the
gtk-3.0 template at the gtk-4.0 one generates a file that is imported and then
ignored in full, which is exactly how Thunar stayed light under a dark rice.

**GTK 3 reads its stylesheet once per process and never again.** Measured on a
running Thunar: rewriting the imported palette changes nothing, touching
`gtk.css` changes nothing, and toggling `gtk-theme` through gsettings changes
nothing. Only a fresh process picks up a new colour — and since Thunar reuses
its running instance over D-Bus, one stale process would serve the old palette
to every window it opens from then on.

**zathura styles itself, not through GTK.** It is a GTK4 client, so it picks up
`gtk-4.0/colors.css` like any other — and none of that reaches the document
view, the statusbar or the completion list, because every one of those is a
zathura setting rather than a CSS rule. It needs its own generated file,
included from `zathurarc`. Search highlights have to be translucent to sit on
top of the text; matugen only emits `rgba()` at full opacity, but GdkRGBA reads
8-digit hex, so the alpha is written in the template.

**Regenerating a palette must never take over the session.** `spicetify apply`
restarts Spotify by default, so every wallpaper change opened it, whatever you
were doing; `-n` patches the bundle and leaves the client alone. The GTK 3 hook
follows the same rule — it quits Thunar only when no window is open, so a
wallpaper change never closes a directory you were browsing.

**A generated file nobody reads is worse than no file.** The vesktop and
spicetify templates were faithfully regenerated for weeks into folders whose
clients were not installed. If a target's client is optional, say so where the
dependency is listed.

**matugen 4.x** refuses to pick between candidate source colours without an
interactive terminal: `--prefer saturation` is mandatory from a keybinding. It
also dropped `arguments = [...]` in `[config.wallpaper]` in favour of a single
command containing `{{ image }}`.

**The `swww` package was renamed `awww`.** Configurations still calling
`swww-daemon` fail silently.

### Thumbnails

**`thumbnail::is-valid` reports false on thumbnails that are perfectly good** —
measured against files Thunar had just rendered and was drawing on screen.
Gating on it throws every cached thumbnail away. The freedesktop rule the
thumbnail carries itself is the one to apply: the source mtime written into
the PNG.

**…and that mtime is not always an integer.** Tumbler's PDF thumbnailer writes
sub-second precision — `1789323098.069184` — so parsing it as an int raises and
declares every PDF stale. Compare on whole seconds, whatever was written.

### The bar and the notch

**The bar's centre is deliberately empty.** `modules-center` holds nothing:
HyprNotch sits there as a layer surface with `exclusive_zone = -1`, which is
what lets it ignore waybar's own exclusive zone and share the same strip. The
clock's hover calendar is off for the same reason — the notch has one.

**Measure the bar, don't recompute it.** Deriving the pill's height from the
font size and padding gave 25 px where waybar's islands were 23. Asking the
compositor for waybar's layer geometry and subtracting the group padding is
exact, and it keeps working when any of those settings change.

**waybar's `font-size: 94%` is not 94%.** It sits on the universal selector, so
it re-applies at every level of waybar's widget tree and the text it actually
draws is far smaller than the figure suggests. Reproducing the percentage
literally gave a pill a third too large — capital letters 10.5 px against the
bar's 8.0. HyprNotch scales the percentage by a factor measured between the two
renders rather than trusting the number.

**Nerd Font player logos are not icon-sized.** The Spotify glyph fills far more
of its em box than the bar's own icons: at the same font size it rendered 12 px
tall against their 9.5. The pill scales its glyph to 78 % so the two match, and
takes `@secondary` — the colour waybar gives every module — instead of the
accent.

**Nerd Font glyphs live in the Unicode private use area.** A stray space after a
glyph (`" "`) visibly shifts the icon inside its pill.

**Nothing in the panel pins it open.** An earlier version pinned on any click,
which meant clicking a tab left the notch stuck open with no obvious way back.
Hover opens and closes; the shortcut is the only thing that pins.

**Turning the shell transparent before the animation ends looks broken.** When
the notch collapses back to nothing, dropping the background immediately left
the panel's text floating over the desktop for the last frames of the shrink.
The ghost state is applied on the animation's `done` signal instead, and fades
out over 140 ms.

**The shell's 1 px border eats into the pill.** Asking the compact box for the
full island height left it a pixel taller than the space inside the border, so
everything in it — the album art most visibly — sat a pixel low. The box asks
for the height minus the border on both sides.

### The rest of the system

**A setting read once at startup is not a setting.** The language file is
shared by the notch, HyprWhale and HyprSettings, and the first two read it only
when they launch — so the switch worked solely because HyprSettings restarts
them, and not at all when anything else wrote the file. They have to watch it,
the way they already watch the palette.

**A script a keybinding calls belongs in the repository.** Ten of them did not,
so a fresh install linked the whole function row and none of the scripts behind
it. The volume keys looked broken for a different reason on top of that:
`volume.sh` calls `pamixer` nineteen times and `pamixer` was never in the
dependency list, so it exited 127 on every press while brightness — whose tool
*was* listed — worked fine.

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
