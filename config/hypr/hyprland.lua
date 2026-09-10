-- Configuration Hyprland au format Lua.
--
-- Portage de hyprland.conf et de ses six fichiers sources, en prevision de
-- Hyprland 0.57 qui supprime le format .conf. Tant que la 0.56 est en place,
-- ce fichier reste hors de ~/.config/hypr/ : Hyprland prefere le Lua au .conf
-- des qu'il le trouve.
--
-- Pour basculer :   cp hyprland.lua ~/.config/hypr/
-- Pour revenir :    rm ~/.config/hypr/hyprland.lua

--------------------------------------------------------------------------
-- COULEURS
--------------------------------------------------------------------------
-- On relit le colors.conf que matugen regenere a chaque fond d'ecran,
-- plutot que de figer des valeurs ici : une seule source de verite.

local function read_colors(path)
    local colors = {}
    local file = io.open(path, "r")
    if not file then
        return colors
    end
    for line in file:lines() do
        local name, hex = line:match("^%$([%w_]+)%s*=%s*rgba?%((%x+)%)")
        if name and hex then
            colors[name] = "rgba(" .. hex .. ")"
        end
    end
    file:close()
    return colors
end

local C = read_colors(os.getenv("HOME") .. "/.config/hypr/colors.conf")
local outline = C.outline or "rgba(9a8f80ff)"
local outline_variant = C.outline_variant or "rgba(4e4639ff)"

--------------------------------------------------------------------------
-- MONITEUR
--------------------------------------------------------------------------

hl.monitor({ output = "eDP-1", mode = "3200x2000@120", position = "0x0", scale = 2 })

--------------------------------------------------------------------------
-- PROGRAMMES
--------------------------------------------------------------------------

local terminal = "kitty"
local fileManager = "thunar"
local menu = "rofi -show drun"
local scripts = os.getenv("HOME") .. "/.config/hypr/scripts"

--------------------------------------------------------------------------
-- DEMARRAGE
--------------------------------------------------------------------------

hl.on("hyprland.start", function()
    hl.exec_cmd("gnome-keyring-daemon --start --components=secrets")
    hl.exec_cmd("vicinae server")
    hl.exec_cmd("nm-applet")
    hl.exec_cmd("waybar")
    hl.exec_cmd("awww-daemon")
    hl.exec_cmd("blueman-applet")
    hl.exec_cmd("swaync")
    hl.exec_cmd("systemctl --user start hyprpolkitagent")
    hl.exec_cmd("hypridle")
    hl.exec_cmd(scripts .. "/HyprNotch.py")
end)

--------------------------------------------------------------------------
-- VARIABLES D'ENVIRONNEMENT
--------------------------------------------------------------------------

hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")

--------------------------------------------------------------------------
-- APPARENCE ET COMPORTEMENT
--------------------------------------------------------------------------

hl.config({
    general = {
        gaps_in = 3,
        gaps_out = { 2, 3, 3, 3 },   -- haut, droite, bas, gauche
        border_size = 1,
        col = {
            active_border = outline,
            inactive_border = outline_variant,
        },
        resize_on_border = false,
        allow_tearing = false,
        layout = "dwindle",
    },

    decoration = {
        rounding = 10,
        rounding_power = 2,
        active_opacity = 1.0,
        inactive_opacity = 0.8,

        shadow = {
            enabled = false,
            range = 4,
            render_power = 3,
            color = 0xee1a1a1a,
        },

        blur = {
            enabled = true,
            size = 5,
            passes = 2,
            ignore_opacity = true,
            new_optimizations = true,
            special = false,
            popups = true,
            xray = true,
            vibrancy = 0.1696,
        },
    },

    dwindle = {
        preserve_split = true,
    },

    master = {
        new_status = "master",
    },

    misc = {
        force_default_wallpaper = 0,
        disable_hyprland_logo = true,
    },

    render = {
        new_render_scheduling = true,
    },

    input = {
        kb_layout = "us",
        follow_mouse = 1,
        sensitivity = 0,
        accel_profile = "flat",
        force_no_accel = 1,
        touchpad = {
            natural_scroll = true,
        },
    },

    animations = {
        enabled = true,
    },
})

hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })

--------------------------------------------------------------------------
-- ANIMATIONS
--------------------------------------------------------------------------

hl.curve("myBezier", { type = "bezier", points = { { 0.05, 0.9 }, { 0.1, 1.05 } } })
hl.curve("been", { type = "bezier", points = { { 0.24, 0.9 }, { 0.25, 0.91 } } })
hl.curve("been2", { type = "bezier", points = { { 0, 0.94 }, { 0.5, 0.99 } } })
hl.curve("menu_decel", { type = "bezier", points = { { 0.1, 1 }, { 0, 1 } } })
hl.curve("linear", { type = "bezier", points = { { 0, 0 }, { 1, 1 } } })
hl.curve("wind", { type = "bezier", points = { { 0.05, 0.9 }, { 0.1, 1.05 } } })
hl.curve("winIn", { type = "bezier", points = { { 0.1, 1.1 }, { 0.1, 1.1 } } })
hl.curve("winOut", { type = "bezier", points = { { 0.3, -0.3 }, { 0, 1 } } })
hl.curve("slow", { type = "bezier", points = { { 0, 0.85 }, { 0.3, 1 } } })
hl.curve("overshot", { type = "bezier", points = { { 0.7, 0.6 }, { 0.1, 1.1 } } })
hl.curve("bounce", { type = "bezier", points = { { 1.1, 1.6 }, { 0.1, 0.85 } } })

hl.animation({ leaf = "windowsIn", enabled = true, speed = 3, bezier = "slow", style = "popin" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 4, bezier = "been", style = "popin 70%" })
hl.animation({ leaf = "windowsMove", enabled = true, speed = 3, bezier = "wind", style = "slide" })
hl.animation({ leaf = "border", enabled = true, speed = 1, bezier = "linear" })
hl.animation({ leaf = "fade", enabled = true, speed = 3, bezier = "overshot" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 3, bezier = "wind" })
hl.animation({ leaf = "windows", enabled = true, speed = 3, bezier = "bounce", style = "popin" })

--------------------------------------------------------------------------
-- ETIQUETTES DE FENETRES
--------------------------------------------------------------------------

hl.window_rule({ name = "tag-video", match = { class = "^([Mm]pv|vlc)$" }, tag = "+multimedia_video" })
hl.window_rule({ name = "tag-settings-net", match = { class = "^(nm-applet|nm-connection-editor|blueman-manager|org.gnome.FileRoller)$" }, tag = "+settings" })
hl.window_rule({ name = "tag-settings-sys", match = { class = "^(org.gnome.DiskUtility|wihotspot(-gui)?)$" }, tag = "+settings" })
hl.window_rule({ name = "tag-monitor", match = { class = "^(org.gnome.SystemMonitor)$" }, tag = "+viewer" })
hl.window_rule({ name = "tag-documents", match = { class = "^(org.gnome.Evince)$" }, tag = "+viewer" })
hl.window_rule({ name = "tag-images", match = { class = "^(eog|org.gnome.Loupe)$" }, tag = "+viewer" })

--------------------------------------------------------------------------
-- REGLES DE FENETRES
--------------------------------------------------------------------------

hl.window_rule({ name = "video-noblur", match = { tag = "multimedia_video*" }, no_blur = true, opacity = 1.0 })
hl.window_rule({ name = "settings-opacity", match = { tag = "settings*" }, opacity = 0.8 })
hl.window_rule({ name = "nautilus", match = { class = "^(org.gnome.Nautilus)$" }, opacity = 0.8 })
hl.window_rule({ name = "editors", match = { class = "^(gedit|org.gnome.TextEditor|mousepad)$" }, opacity = 0.9 })
hl.window_rule({ name = "pavucontrol-opacity", match = { class = "^(org.pulseaudio.pavucontrol)$" }, opacity = 0.9 })
hl.window_rule({ name = "kitty-opacity", match = { class = "^(kitty)$" }, opacity = 0.9 })
hl.window_rule({ name = "chat-opacity", match = { class = "^(discord|vesktop|org.telegram.desktop)$" }, opacity = "0.85 override 0.7 override 1 override" })
hl.window_rule({ name = "spotify-opacity", match = { class = "^(Spotify)$" }, opacity = "0.8 override 0.6 override 1 override" })
hl.window_rule({ name = "zen-opacity", match = { class = "^(zen)$" }, opacity = "0.9 override 0.7 override 1 override" })

hl.window_rule({ name = "float-settings", match = { tag = "settings*" }, float = true })
hl.window_rule({ name = "float-viewer", match = { tag = "viewer*" }, float = true })
hl.window_rule({ name = "float-video", match = { tag = "multimedia_video*" }, float = true, size = "900 506" })
hl.window_rule({ name = "float-pavucontrol", match = { class = "^(org.pulseaudio.pavucontrol)$" }, float = true, size = "50% 60%" })

hl.window_rule({ name = "suppress-maximize", match = { class = ".*" }, suppress_event = "maximize" })
hl.window_rule({
    name = "fix-xwayland-drags",
    match = { class = "^$", title = "^$", xwayland = true, float = true, fullscreen = false, pin = false },
    no_focus = true,
})

hl.window_rule({ name = "save-dialog", match = { title = "^(Save As|Save a File|Pick Files)$" }, float = true, size = "50% 60%", center = true })
hl.window_rule({ name = "open-dialog", match = { initial_title = "(Open Files)" }, float = true, size = "70% 60%" })

-- les quatre applications maison
hl.window_rule({ name = "hyprsettings", match = { class = "dev.local.HyprSettings" }, float = true, size = "580 720", center = true })
hl.window_rule({ name = "hyprkeys", match = { class = "dev.local.HyprKeys" }, float = true, size = "680 780", center = true })
hl.window_rule({ name = "hyprwhale", match = { class = "dev.local.HyprWhale" }, float = true, move = "1178 66" })

--------------------------------------------------------------------------
-- REGLES DE COUCHES
--------------------------------------------------------------------------

hl.layer_rule({ match = { namespace = "waybar" }, blur = true, ignore_alpha = 0.5 })
hl.layer_rule({ match = { tag = "notif*" }, ignore_alpha = 0.5 })
hl.layer_rule({ match = { namespace = "logout_dialog" }, blur = true })
hl.layer_rule({ match = { namespace = "hyprnotch" }, blur = true, ignore_alpha = 0.2, xray = false })
hl.layer_rule({ match = { namespace = "swaync-control-center" }, blur = true, ignore_alpha = 0.5, xray = false })
hl.layer_rule({ match = { namespace = "swaync-notification-window" }, blur = true, ignore_alpha = 0.5, xray = false })

--------------------------------------------------------------------------
-- RACCOURCIS
--------------------------------------------------------------------------

local mod = "SUPER"

-- applications
hl.bind(mod .. " + Return", hl.dsp.exec_cmd(terminal))
hl.bind(mod .. " + SHIFT + Return", hl.dsp.exec_cmd("[float; size 800 550] " .. terminal))
hl.bind(mod .. " + E", hl.dsp.exec_cmd(fileManager))
hl.bind(mod .. " + SHIFT + E", hl.dsp.exec_cmd("kitty yazi"))
hl.bind(mod .. " + W", hl.dsp.exec_cmd(menu))
hl.bind("ALT + space", hl.dsp.exec_cmd("vicinae toggle"))
hl.bind(mod .. " + B", hl.dsp.exec_cmd("helium-browser"))
hl.bind(mod .. " + D", hl.dsp.exec_cmd("discord"))
hl.bind(mod .. " + C", hl.dsp.exec_cmd("claude-desktop"))
hl.bind(mod .. " + S", hl.dsp.exec_cmd("spotify-launcher"))
hl.bind(mod .. " + ALT + C", hl.dsp.exec_cmd("hyprpicker -a"))
hl.bind(mod .. " + L", hl.dsp.exec_cmd(scripts .. "/hyprlock.sh"))
hl.bind(mod .. " + SHIFT + S", hl.dsp.exec_cmd(scripts .. "/screenshot.sh"))

-- fenetres
hl.bind(mod .. " + Q", hl.dsp.window.close())
hl.bind(mod .. " + SHIFT + Q", hl.dsp.exec_cmd(scripts .. "/KillActiveProcess.sh"))
hl.bind(mod .. " + space", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mod .. " + SHIFT + F", hl.dsp.window.fullscreen())
hl.bind(mod .. " + P", hl.dsp.window.pseudo())
hl.bind(mod .. " + J", hl.dsp.layout("togglesplit"))
hl.bind("CTRL + ALT + Delete", hl.dsp.exit())

-- apparence
hl.bind(mod .. " + Z", hl.dsp.exec_cmd(scripts .. "/wppicker.sh"))
hl.bind(mod .. " + R", hl.dsp.exec_cmd(scripts .. "/wbrestart.sh"))
hl.bind(mod .. " + CTRL + B", hl.dsp.exec_cmd(scripts .. "/WaybarStyles.sh"))
hl.bind(mod .. " + ALT + B", hl.dsp.exec_cmd(scripts .. "/WaybarLayout.sh"))
hl.bind(mod .. " + H", hl.dsp.exec_cmd("pkill -SIGUSR1 waybar"))

-- config et aide
hl.bind(mod .. " + slash", hl.dsp.exec_cmd(scripts .. "/CheatSheet.sh"))
hl.bind(mod .. " + SHIFT + slash", hl.dsp.exec_cmd(scripts .. "/HyprKeys.py"))
hl.bind(mod .. " + N", hl.dsp.exec_cmd(
    "pkill -SIGUSR2 -f HyprNotch.py || " .. scripts .. "/HyprNotch.py"))
hl.bind(mod .. " + SHIFT + K", hl.dsp.exec_cmd(scripts .. "/HyprSettings.py"))
hl.bind(mod .. " + K", hl.dsp.exec_cmd("[float; size 1100 750] kitty nano " ..
    os.getenv("HOME") .. "/.config/hypr/configs/keybinds.conf"))

-- focus et deplacement
for key, dir in pairs({ left = "left", right = "right", up = "up", down = "down" }) do
    hl.bind(mod .. " + " .. key, hl.dsp.focus({ direction = dir }))
    hl.bind(mod .. " + CTRL + " .. key, hl.dsp.window.move({ direction = dir }))
end

hl.bind(mod .. " + SHIFT + left", hl.dsp.window.resize({ x = -50, y = 0 }), { repeating = true })
hl.bind(mod .. " + SHIFT + right", hl.dsp.window.resize({ x = 50, y = 0 }), { repeating = true })
hl.bind(mod .. " + SHIFT + up", hl.dsp.window.resize({ x = 0, y = -50 }), { repeating = true })
hl.bind(mod .. " + SHIFT + down", hl.dsp.window.resize({ x = 0, y = 50 }), { repeating = true })

-- espaces de travail
for i = 1, 10 do
    local key = i % 10
    hl.bind(mod .. " + " .. key, hl.dsp.focus({ workspace = i }))
    hl.bind(mod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = i }))
end

hl.bind(mod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mod .. " + mouse_up", hl.dsp.focus({ workspace = "e-1" }))
hl.bind(mod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
hl.bind(mod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- touches multimedia
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd(scripts .. "/volume.sh --inc"), { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd(scripts .. "/volume.sh --dec"), { locked = true, repeating = true })
hl.bind("XF86AudioMute", hl.dsp.exec_cmd(scripts .. "/volume.sh --toggle"), { locked = true, repeating = true })
hl.bind("XF86AudioMicMute", hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"), { locked = true, repeating = true })
hl.bind("XF86MonBrightnessUp", hl.dsp.exec_cmd(scripts .. "/brightness.sh --inc"), { locked = true, repeating = true })
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd(scripts .. "/brightness.sh --dec"), { locked = true, repeating = true })

hl.bind("XF86AudioNext", hl.dsp.exec_cmd("playerctl next"), { locked = true })
hl.bind("XF86AudioPause", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPrev", hl.dsp.exec_cmd("playerctl previous"), { locked = true })
