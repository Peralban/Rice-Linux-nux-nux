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
-- REGLAGES
--------------------------------------------------------------------------
-- HyprSettings ecrit dans looknfeel.conf et input.conf. Si ce fichier
-- figeait ses propres valeurs, il les ecraserait a chaque demarrage et le
-- panneau semblerait « oublier » tout ce qu'on y regle. On relit donc les
-- .conf, comme on relit deja colors.conf pour la palette : une seule
-- source de verite, et le panneau fait foi.

local configs = os.getenv("HOME") .. "/.config/hypr/configs"

local function read_conf(path)
    local values, stack = {}, {}
    local file = io.open(path, "r")
    if not file then
        return values
    end
    for raw in file:lines() do
        -- Lua 5.4 : la variable de boucle est constante, on recopie.
        local line = raw:gsub("#.*$", "")
        local section = line:match("^%s*([%w_]+)%s*{%s*$")
        if section then
            stack[#stack + 1] = section
        elseif line:match("^%s*}%s*$") then
            stack[#stack] = nil
        else
            local key, value = line:match("^%s*([%w_.]+)%s*=%s*(.-)%s*$")
            if key then
                local prefix = table.concat(stack, ":")
                -- « col.active_border » designe un chemin, pas un nom pointe
                key = key:gsub("%.", ":")
                values[(prefix ~= "" and prefix .. ":" or "") .. key] = value
            end
        end
    end
    file:close()
    return values
end

local LOOK = read_conf(configs .. "/looknfeel.conf")
local IN = read_conf(configs .. "/input.conf")

local function num(t, key, fallback)
    return tonumber(t[key]) or fallback
end

local function bool(t, key, fallback)
    local value = t[key]
    if value == "true" then return true end
    if value == "false" then return false end
    return fallback
end

local function str(t, key, fallback)
    local value = t[key]
    if value == nil or value == "" then return fallback end
    return value
end

-- Les ecarts sont un type « css_gap ». Le parseur veut un entier ou une
-- table aux quatre cotes NOMMES : la forme tableau { 2, 3, 3, 3 } est
-- acceptee sans broncher puis ignoree, et les ecarts retombent a zero.
-- C'est ce qui arrivait a gaps_out depuis le passage au Lua.
local function gaps(t, key, fallback)
    local value = t[key]
    if value == nil or value == "" then return fallback end
    local sides = {}
    for part in value:gmatch("[^,]+") do
        sides[#sides + 1] = tonumber(part:match("^%s*(.-)%s*$"))
    end
    if #sides == 0 or sides[1] == nil then return fallback end
    if #sides == 1 then return sides[1] end
    while #sides < 4 do sides[#sides + 1] = sides[#sides] end
    -- .conf : haut, droite, bas, gauche
    return { top = sides[1], right = sides[2], bottom = sides[3], left = sides[4] }
end

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
        gaps_in = gaps(LOOK, "general:gaps_in", 3),
        gaps_out = gaps(LOOK, "general:gaps_out",
            { top = 2, right = 3, bottom = 3, left = 3 }),
        border_size = num(LOOK, "general:border_size", 1),
        col = {
            -- Les bordures viennent de la palette, pas du .conf : il n'y
            -- ecrit que « $outline », que seul le parseur legacy resout.
            active_border = outline,
            inactive_border = outline_variant,
        },
        resize_on_border = bool(LOOK, "general:resize_on_border", false),
        allow_tearing = bool(LOOK, "general:allow_tearing", false),
        layout = str(LOOK, "general:layout", "dwindle"),
    },

    decoration = {
        rounding = num(LOOK, "decoration:rounding", 10),
        rounding_power = num(LOOK, "decoration:rounding_power", 2),
        active_opacity = num(LOOK, "decoration:active_opacity", 1.0),
        inactive_opacity = num(LOOK, "decoration:inactive_opacity", 0.8),

        shadow = {
            enabled = bool(LOOK, "decoration:shadow:enabled", false),
            range = num(LOOK, "decoration:shadow:range", 4),
            render_power = num(LOOK, "decoration:shadow:render_power", 3),
            color = 0xee1a1a1a,
        },

        blur = {
            enabled = bool(LOOK, "decoration:blur:enabled", true),
            size = num(LOOK, "decoration:blur:size", 5),
            passes = num(LOOK, "decoration:blur:passes", 2),
            ignore_opacity = bool(LOOK, "decoration:blur:ignore_opacity", true),
            new_optimizations = bool(LOOK, "decoration:blur:new_optimizations", true),
            special = bool(LOOK, "decoration:blur:special", false),
            popups = bool(LOOK, "decoration:blur:popups", true),
            xray = bool(LOOK, "decoration:blur:xray", true),
            vibrancy = num(LOOK, "decoration:blur:vibrancy", 0.1696),
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
        kb_layout = str(IN, "input:kb_layout", "us"),
        follow_mouse = num(IN, "input:follow_mouse", 1),
        sensitivity = num(IN, "input:sensitivity", 0),
        accel_profile = str(IN, "input:accel_profile", "flat"),
        force_no_accel = num(IN, "input:force_no_accel", 1),
        touchpad = {
            natural_scroll = bool(IN, "input:touchpad:natural_scroll", true),
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

-- les quatre panneaux maison (les notes se tuilent, pas de regle)
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
hl.bind(mod .. " + N", hl.dsp.exec_cmd(scripts .. "/HyprNotes.py"))
hl.bind(mod .. " + SHIFT + N", hl.dsp.exec_cmd(
    "pkill -SIGUSR2 -f HyprNotch.py || " .. scripts .. "/HyprNotch.py"))
hl.bind(mod .. " + SHIFT + K", hl.dsp.exec_cmd(scripts .. "/HyprSettings.py"))
hl.bind(mod .. " + K", hl.dsp.exec_cmd("[float; size 1100 750] kitty nano " ..
    os.getenv("HOME") .. "/.config/hypr/configs/keybinds.conf"))

-- focus et deplacement
for key, dir in pairs({ left = "left", right = "right", up = "up", down = "down" }) do
    hl.bind(mod .. " + " .. key, hl.dsp.focus({ direction = dir }))
    hl.bind(mod .. " + CTRL + " .. key, hl.dsp.window.move({ direction = dir }))
end

hl.bind(mod .. " + SHIFT + left", hl.dsp.window.resize({ x = -50, y = 0, relative = true }), { repeating = true })
hl.bind(mod .. " + SHIFT + right", hl.dsp.window.resize({ x = 50, y = 0, relative = true }), { repeating = true })
hl.bind(mod .. " + SHIFT + up", hl.dsp.window.resize({ x = 0, y = -50, relative = true }), { repeating = true })
hl.bind(mod .. " + SHIFT + down", hl.dsp.window.resize({ x = 0, y = 50, relative = true }), { repeating = true })

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
