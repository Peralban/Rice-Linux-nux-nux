-- Hyprland configuration, in Lua.
--
-- A port of hyprland.conf and its six source files, in anticipation of
-- Hyprland 0.57 dropping the .conf format. While 0.56 is still in place this
-- file stays outside ~/.config/hypr/: Hyprland prefers Lua over the .conf as
-- soon as it finds one.
--
-- Pour basculer :   cp hyprland.lua ~/.config/hypr/
-- Pour revenir :    rm ~/.config/hypr/hyprland.lua

--------------------------------------------------------------------------
-- COULEURS
--------------------------------------------------------------------------
-- We re-read the colors.conf matugen regenerates on every wallpaper, rather
-- than freezing values here: one source of truth.

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
-- HyprSettings writes to looknfeel.conf and input.conf. If this file froze
-- values of its own it would overwrite them on every startup and the panel
-- would appear to "forget" everything set in it. So we re-read the .conf
-- files, just as colors.conf is already re-read for the palette: one source
-- of truth, and the panel is authoritative.

local configs = os.getenv("HOME") .. "/.config/hypr/configs"

local function read_conf(path)
    local values, stack = {}, {}
    local file = io.open(path, "r")
    if not file then
        return values
    end
    for raw in file:lines() do
        -- Lua 5.4: the loop variable is constant, so copy it.
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

-- Gaps are a "css_gap" type. The parser wants either an integer or a table
-- with the four sides NAMED: the array form { 2, 3, 3, 3 } is accepted without
-- complaint, then ignored, and the gaps fall back to zero. That is what had
-- been happening to gaps_out ever since the move to Lua.
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
            -- Borders come from the palette, not the .conf: that only writes
            -- "$outline", which only the legacy parser resolves.
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
        -- Accents the way macOS does them: a dead key held behind AltGr, so
        -- ` and ' keep typing themselves. The `intl` variant puts the dead
        -- keys on the bare keys instead, which makes a shell or a C string a
        -- minefield. AltGr+` then e -> e-grave, AltGr+' then e -> e-acute,
        -- AltGr+6 then e -> e-circumflex, AltGr+, -> c-cedilla.
        kb_variant = str(IN, "input:kb_variant", "altgr-intl"),
        kb_options = str(IN, "input:kb_options", "lv3:ralt_switch"),
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

-- the in-house panels (notes tile, so no rule)
hl.window_rule({ name = "hyprsettings", match = { class = "dev.local.HyprSettings" }, float = true, size = "580 720", center = true })
hl.window_rule({ name = "hyprkeys", match = { class = "dev.local.HyprKeys" }, float = true, size = "680 780", center = true })
hl.window_rule({ name = "hyprwhale", match = { class = "dev.local.HyprWhale" }, float = true, move = "1178 66" })
-- under the sound module; the app pins its own top-right corner afterwards
hl.window_rule({ name = "hyprduo", match = { class = "dev.local.HyprDuo" }, float = true,
    move = "(monitor_w-window_w-12) 66" })

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
-- The shortcuts live in configs/keybinds.conf, not here. HyprKeys edits that
-- file and the cheat sheet lists it; when this file kept a copy of its own,
-- both kept working on a list Hyprland no longer read, and every shortcut
-- added through HyprKeys was silently dead. So, as with looknfeel.conf above,
-- the .conf is read and translated: one source of truth, and the editor is
-- authoritative.
--
-- Anything this cannot translate is skipped and written, with its line, to
-- $XDG_RUNTIME_DIR/hypr-skipped-binds, which HyprKeys reads back after saving.

local bindfile = configs .. "/keybinds.conf"
local skipped_log = (os.getenv("XDG_RUNTIME_DIR") or "/tmp") .. "/hypr-skipped-binds"

local function trim(text)
    return (text:gsub("^%s+", ""):gsub("%s+$", ""))
end

local directions = { l = "left", r = "right", u = "up", d = "down",
                     left = "left", right = "right", up = "up", down = "down" }

-- A workspace argument: a number where it is one ("3"), as is otherwise
-- ("e+1", "special:magic").
local function workspace(arg)
    return tonumber(arg) or arg
end

-- dispatcher name -> function(argument, is_mouse_bind) -> hl.dsp action
local dispatchers = {
    exec = function(arg) return hl.dsp.exec_cmd(arg) end,
    killactive = function() return hl.dsp.window.close() end,
    togglefloating = function() return hl.dsp.window.float({ action = "toggle" }) end,
    pseudo = function() return hl.dsp.window.pseudo() end,
    fullscreen = function() return hl.dsp.window.fullscreen() end,
    layoutmsg = function(arg) return hl.dsp.layout(arg) end,
    exit = function() return hl.dsp.exit() end,
    movefocus = function(arg)
        local dir = directions[arg]
        return dir and hl.dsp.focus({ direction = dir })
    end,
    movewindow = function(arg, mouse)
        if mouse then return hl.dsp.window.drag() end
        local dir = directions[arg]
        return dir and hl.dsp.window.move({ direction = dir })
    end,
    resizewindow = function(_, mouse)
        return mouse and hl.dsp.window.resize()
    end,
    resizeactive = function(arg)
        local x, y = arg:match("^(%-?%d+)%s+(%-?%d+)$")
        return x and hl.dsp.window.resize({ x = tonumber(x), y = tonumber(y), relative = true })
    end,
    workspace = function(arg)
        return arg ~= "" and hl.dsp.focus({ workspace = workspace(arg) })
    end,
    movetoworkspace = function(arg)
        return arg ~= "" and hl.dsp.window.move({ workspace = workspace(arg) })
    end,
}

-- bindel = e + l. Only the flags this file uses have a Lua spelling here.
local flags = { e = "repeating", l = "locked", m = "mouse" }

-- $mainMod and friends: the ones hyprland.conf defined, then whatever the
-- bind file defines itself.
local vars = { terminal = terminal, fileManager = fileManager, menu = menu, mainMod = "SUPER" }

local function expand(text)
    return (text:gsub("%$([%a_][%w_]*)", function(name) return vars[name] end))
end

local function load_binds(path)
    local file = io.open(path, "r")
    if not file then return 0, {} end
    local count, skipped, number = 0, {}, 0
    for raw in file:lines() do
        number = number + 1
        -- HyprKeys reads a comment from the first #, so the same rule here
        local line = raw:gsub("#.*$", "")
        local name, value = line:match("^%s*%$([%a_][%w_]*)%s*=%s*(.-)%s*$")
        if name then
            vars[name] = value
        else
            local kind, body = line:match("^%s*bind(%a*)%s*=%s*(.-)%s*$")
            if kind then
                local mods, key, dispatcher, arg = body:match("^([^,]*),([^,]*),([^,]*),?(.*)$")
                local options = {}
                for letter in kind:gmatch(".") do
                    if flags[letter] then options[flags[letter]] = true end
                end
                local action
                if mods then
                    local make = dispatchers[trim(dispatcher)]
                    action = make and make(expand(trim(arg)), options.mouse)
                end
                if action then
                    local combo = {}
                    for part in expand(mods):gmatch("%S+") do combo[#combo + 1] = part end
                    combo[#combo + 1] = trim(key)
                    -- One key name Hyprland refuses must not take every line
                    -- after it down with it: an error would end the file here.
                    local ok, err = pcall(hl.bind, table.concat(combo, " + "), action,
                                          next(options) and options or nil)
                    if ok then
                        count = count + 1
                    else
                        skipped[#skipped + 1] = number .. "\t" .. trim(raw) .. "\t" .. tostring(err)
                    end
                else
                    skipped[#skipped + 1] = number .. "\t" .. trim(raw)
                end
            end
        end
    end
    file:close()
    return count, skipped
end

local count, skipped = load_binds(bindfile)

local log = io.open(skipped_log, "w")
if log then
    for _, entry in ipairs(skipped) do log:write(entry, "\n") end
    log:close()
end

-- An unreadable or emptied file must not leave the desktop without a
-- keyboard: the shortcuts needed to repair it, and nothing more.
if count == 0 then
    hl.bind("SUPER + Return", hl.dsp.exec_cmd(terminal))
    hl.bind("SUPER + Q", hl.dsp.window.close())
    hl.bind("SUPER + SHIFT + slash", hl.dsp.exec_cmd(scripts .. "/HyprKeys.py"))
    hl.bind("SUPER + K", hl.dsp.exec_cmd("[float; size 1100 750] kitty nano " .. bindfile))
    hl.bind("CTRL + ALT + Delete", hl.dsp.exit())
end
