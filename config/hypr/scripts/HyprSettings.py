#!/usr/bin/env python3
"""Panneau de réglages d'apparence pour Hyprland (bilingue FR / EN).

Lit et écrit ~/.config/hypr/configs/looknfeel.conf, et applique chaque
changement en direct via `hyprctl keyword`.
"""

import io
import json
import os
import re
import signal
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

CONF = os.path.expanduser("~/.config/hypr/configs/looknfeel.conf")
INPUT_CONF = os.path.expanduser("~/.config/hypr/configs/input.conf")


WAYBAR_CONF = os.path.realpath(os.path.expanduser("~/.config/waybar/config"))

WAYBAR_MODULES = os.path.expanduser("~/.config/waybar/Modules")
WAYBAR_STYLE = os.path.realpath(os.path.expanduser("~/.config/waybar/style.css"))

# le CSS accepte des mots-cles : on les ramene a leur equivalent numerique
WEIGHT_WORDS = {
    "thin": "100", "extralight": "200", "light": "300", "normal": "400",
    "regular": "400", "medium": "500", "semibold": "600", "bold": "700",
    "extrabold": "800",
}


# une bulle = un bloc CSS portant le fond semi-transparent caracteristique
BUBBLE = re.compile(r"background-color: alpha\(@surface_container, 0\.75\);.*?\}", re.S)


def _bubble_sub(text, prop, value, shorthand=False):
    def in_block(block):
        body = block.group(0)
        if shorthand:
            return re.sub(r"(margin:\s*0 0 0 )(\d+)(px)",
                          lambda m: m.group(1) + value + m.group(3), body)
        return re.sub(r"(%s:\s*)(\d+)(px)" % prop,
                      lambda m: m.group(1) + value + m.group(3), body)
    return BUBBLE.sub(in_block, text)


def read_style():
    out = {}
    try:
        text = io.open(WAYBAR_STYLE, encoding="utf-8").read()
    except OSError:
        return out
    found = re.search(r"font-weight:\s*([A-Za-z0-9]+)\s*;", text)
    if found:
        raw = found.group(1).lower()
        out["waybar:font-weight"] = raw if raw.isdigit() else WEIGHT_WORDS.get(raw, "400")
    found = re.search(r"font-size:\s*(\d+)%", text)
    if found:
        out["waybar:font-size"] = found.group(1)

    bubble = BUBBLE.search(text)
    if bubble:
        gap = re.search(r"margin:\s*0 0 0 (\d+)px", bubble.group(0))
        if gap:
            out["waybar:pill-gap"] = gap.group(1)
        pad = re.search(r"padding-top:\s*(\d+)px", bubble.group(0))
        if pad:
            out["waybar:pill-pad"] = pad.group(1)
        padx = re.search(r"padding-left:\s*(\d+)px", bubble.group(0))
        if padx:
            out["waybar:pill-padx"] = padx.group(1)
    return out


def write_style(values):
    try:
        text = io.open(WAYBAR_STYLE, encoding="utf-8").read()
    except OSError:
        return
    if "waybar:font-weight" in values:
        text = re.sub(r"(font-weight:\s*)([A-Za-z0-9]+)(\s*;)",
                      lambda m: m.group(1) + values["waybar:font-weight"] + m.group(3),
                      text, count=1)
    if "waybar:font-size" in values:
        text = re.sub(r"(font-size:\s*)(\d+)(%)",
                      lambda m: m.group(1) + values["waybar:font-size"] + m.group(3),
                      text, count=1)
    if "waybar:pill-gap" in values:
        text = _bubble_sub(text, None, values["waybar:pill-gap"], shorthand=True)
    if "waybar:pill-pad" in values:
        pad = values["waybar:pill-pad"]
        text = _bubble_sub(text, "padding-top", pad)
        text = _bubble_sub(text, "padding-bottom", pad)
    if "waybar:pill-padx" in values:
        padx = values["waybar:pill-padx"]
        text = _bubble_sub(text, "padding-left", padx)
        text = _bubble_sub(text, "padding-right", padx)

    io.open(WAYBAR_STYLE, "w", encoding="utf-8").write(text)

TRAY_RE = re.compile(r'("tray"\s*:\s*\{[^}]*?"icon-size"\s*:\s*)(\d+)', re.S)

WB_KEYS = {
    "waybar:height": "height",
    "waybar:spacing": "spacing",
    "waybar:margin-top": "margin-top",
    "waybar:margin-side": "margin-left",
}


def read_waybar():
    """La config waybar est du JSON commenté : on cible les clés au regex."""
    out = {}
    try:
        text = io.open(WAYBAR_CONF, encoding="utf-8").read()
    except OSError:
        return out
    for path, key in WB_KEYS.items():
        found = re.search(r'"%s"\s*:\s*(-?\d+)' % re.escape(key), text)
        if found:
            out[path] = found.group(1)
    out.setdefault("waybar:height", "0")
    try:
        found = TRAY_RE.search(io.open(WAYBAR_MODULES, encoding="utf-8").read())
        if found:
            out["waybar:tray"] = found.group(2)
    except OSError:
        pass
    out.update(read_style())
    return out


def write_waybar(values):
    try:
        text = io.open(WAYBAR_CONF, encoding="utf-8").read()
    except OSError:
        return
    for path, key in WB_KEYS.items():
        if path not in values:
            continue
        value = values[path]
        pattern = re.compile(r'("%s"\s*:\s*)(-?\d+)' % re.escape(key))
        if pattern.search(text):
            text = pattern.sub(lambda m: m.group(1) + value, text, count=1)
        else:
            text = re.sub(r'("spacing"\s*:\s*-?\d+,)',
                          lambda m: m.group(1) + '\n"%s": %s,' % (key, value),
                          text, count=1)
    if "waybar:margin-side" in values:
        side = values["waybar:margin-side"]
        text = re.sub(r'("margin-right"\s*:\s*)(-?\d+)',
                      lambda m: m.group(1) + side, text, count=1)
    io.open(WAYBAR_CONF, "w", encoding="utf-8").write(text)

    write_style(values)

    if "waybar:tray" in values:
        try:
            mods = io.open(WAYBAR_MODULES, encoding="utf-8").read()
            new = TRAY_RE.sub(lambda m: m.group(1) + values["waybar:tray"], mods, count=1)
            io.open(WAYBAR_MODULES, "w", encoding="utf-8").write(new)
        except OSError:
            pass


NOTCH_CONF = os.path.expanduser("~/.config/hypr/scripts/.hyprnotch.json")

# Les réglages du notch ne vivent pas dans hyprland.conf mais dans son
# propre JSON. Ce qui suit « notch: » est le chemin dans ce fichier.
NOTCH_KEYS = (
    "notch:widgets.media",
    "notch:widgets.calendar",
    "notch:widgets.system",
    "notch:widgets.files",
    "notch:widgets.airdrop",
    "notch:widgets.notes",
    "notch:notch.hover_to_open",
    "notch:notch.default_page",
)

NOTCH_PAGES = ["calendar", "system", "files", "airdrop", "notes"]


def _notch_read_json():
    try:
        data = json.load(io.open(NOTCH_CONF, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_notch():
    data = _notch_read_json()
    out = {}
    for path in NOTCH_KEYS:
        node = data
        for part in path[len("notch:"):].split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            continue
        out[path] = {True: "true", False: "false"}.get(node, str(node))
    return out


def write_notch(values):
    """Réécrit le JSON du notch sans perdre les clés qu'on n'affiche pas :
    l'utilisateur peut y avoir mis une géométrie ou un moniteur à la main."""
    touched = [p for p in NOTCH_KEYS if p in values]
    if not touched:
        return False
    data = _notch_read_json()
    for path in touched:
        parts = path[len("notch:"):].split(".")
        node = data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        raw = values[path]
        node[parts[-1]] = raw == "true" if raw in ("true", "false") else raw
    try:
        os.makedirs(os.path.dirname(NOTCH_CONF), exist_ok=True)
        with open(NOTCH_CONF, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
    except OSError:
        return False
    return True


def restart_notch():
    """Les onglets se construisent au démarrage : un signal ne suffirait pas
    à faire apparaître ou disparaître l'un d'eux, il faut relancer.

    Le motif porte des crochets pour que `pkill` ne se reconnaisse pas
    lui-même dans sa propre ligne de commande."""
    subprocess.run(["pkill", "-f", "HyprNotch[.]py"], capture_output=True, check=False)
    try:
        subprocess.Popen([os.path.expanduser("~/.config/hypr/scripts/HyprNotch.py")],
                         start_new_session=True)
    except OSError:
        pass


def file_for(path):
    """Chaque reglage vit dans son fichier d'origine."""
    return INPUT_CONF if path.startswith("input:") else CONF
LANG_FILE = os.path.expanduser("~/.config/hypr/scripts/.hyprsettings-lang")

# --------------------------------------------------------------------------
# Traductions
# --------------------------------------------------------------------------

T = {
    "fr": {
        "window": "Apparence Hyprland",
        "save": "Enregistrer",
        "reload": "Recharger depuis le fichier",
        "saved": "Enregistré dans looknfeel.conf",
        "reloaded": "Valeurs rechargées depuis le fichier",
        "lang_menu": "Langue — réglages, notch et docker",
        "hint": ("Les changements s'appliquent en direct",
                 "Rien n'est écrit tant que tu n'as pas cliqué sur Enregistrer."),
        "g_spacing": ("Espacements", "Marges autour et entre les fenêtres"),
        "gaps_in": ("Entre les fenêtres", "Espace séparant deux fenêtres voisines"),
        "gaps_out": ("Bord de l'écran", "Marge entre les fenêtres et le bord"),
        "gaps_top": ("Sous la waybar", "Espace entre la barre et le haut des fenêtres"),
        "border": ("Épaisseur de bordure", "Trait coloré autour de la fenêtre active"),
        "g_deco": ("Décoration", "Forme et transparence des fenêtres"),
        "rounding": ("Arrondi des coins", "0 pour des coins parfaitement carrés"),
        "active_op": ("Opacité — fenêtre active", "1.00 = totalement opaque"),
        "inactive_op": ("Opacité — fenêtres inactives", "Plus bas = arrière-plan plus discret"),
        "g_blur": ("Flou", "Attention : le coût GPU grimpe vite avec les passes"),
        "blur_on": ("Activer le flou", "Coupe entièrement l'effet si désactivé"),
        "blur_size": ("Intensité", "Rayon du flou appliqué derrière les fenêtres"),
        "blur_passes": ("Passes", "Chaque passe supplémentaire coûte cher — 2 est un bon compromis"),
        "g_notch": ("Notch", "HyprNotch — appliqué à l'enregistrement, le notch redémarre"),
        "nk_media": ("Lecteur média", "La pastille de lecture et son panneau"),
        "nk_calendar": ("Calendrier", "Le mois en cours, dans la colonne de droite"),
        "nk_system": ("Système", "Processeur, mémoire, batterie, réseau"),
        "nk_files": ("Étagère à fichiers", "Déposer ici, récupérer ailleurs"),
        "nk_airdrop": ("AirDrop", "Envoi et réception vers les appareils Apple"),
        "nk_notes": ("Notes", "La note épinglée depuis HyprNotes, cochable ici"),
        "nk_hover": ("Ouvrir au survol", "Sans ça, seul Super+N ouvre le panneau"),
        "nk_page": ("Onglet par défaut", "Celui qui s'affiche à l'ouverture"),
        "g_input": ("Souris et clavier", "Périphériques de saisie"),
        "sensitivity": ("Sensibilité de la souris", "0 = vitesse brute du capteur, sans correction"),
        "natural_scroll": ("Défilement naturel", "Le contenu suit le doigt, comme sur un téléphone"),
        "accel": ("Accélération du pointeur", "« flat » garde une vitesse constante — préféré pour viser juste"),
        "kb_layout": ("Disposition du clavier", "Mets « fr » si tes touches sont en AZERTY"),
        "g_waybar": ("Barre du haut", "Waybar — appliqué à l'enregistrement, la barre redémarre"),
        "wb_height": ("Hauteur", "0 = automatique, calculée depuis la taille de police"),
        "wb_spacing": ("Espacement des modules", "Écart entre deux éléments de la barre"),
        "wb_margin_top": ("Marge haute", "Distance entre la barre et le haut de l'écran"),
        "wb_margin_side": ("Marges latérales", "Retrait à gauche et à droite"),
        "wb_tray": ("Taille des icônes système", "C'est ce réglage qui commande vraiment l'épaisseur de la barre"),
        "wb_font_size": ("Taille du texte", "En pourcentage de la police du système"),
        "wb_font_weight": ("Épaisseur du texte", "400 = normal, 700 = gras — ta police en propose 8 niveaux"),
        "wb_pill_gap": ("Écart entre les bulles", "Espace séparant deux groupes de modules"),
        "wb_pill_pad": ("Hauteur des bulles", "Rembourrage au-dessus et en dessous du contenu"),
        "wb_pill_padx": ("Largeur des bulles", "Rembourrage à gauche et à droite du contenu"),
    },
    "en": {
        "window": "Hyprland Appearance",
        "save": "Save",
        "reload": "Reload from file",
        "saved": "Saved to looknfeel.conf",
        "reloaded": "Values reloaded from file",
        "lang_menu": "Language — settings, notch and dock",
        "hint": ("Changes apply instantly",
                 "Nothing is written to disk until you click Save."),
        "g_spacing": ("Spacing", "Margins around and between windows"),
        "gaps_in": ("Between windows", "Gap separating two neighbouring windows"),
        "gaps_out": ("Screen edge", "Margin between windows and the screen border"),
        "gaps_top": ("Below the waybar", "Space between the bar and the top of windows"),
        "border": ("Border width", "Coloured outline around the focused window"),
        "g_deco": ("Decoration", "Window shape and transparency"),
        "rounding": ("Corner rounding", "0 for perfectly square corners"),
        "active_op": ("Opacity — focused window", "1.00 = fully opaque"),
        "inactive_op": ("Opacity — unfocused windows", "Lower means a more subdued background"),
        "g_blur": ("Blur", "Careful: GPU cost climbs fast with each pass"),
        "blur_on": ("Enable blur", "Turns the effect off entirely"),
        "blur_size": ("Strength", "Blur radius applied behind windows"),
        "blur_passes": ("Passes", "Each extra pass is expensive — 2 is a good balance"),
        "g_notch": ("Notch", "HyprNotch — applied on save, the notch restarts"),
        "nk_media": ("Media player", "The playback pill and its panel"),
        "nk_calendar": ("Calendar", "The current month, in the right column"),
        "nk_system": ("System", "CPU, memory, battery, network"),
        "nk_files": ("File shelf", "Drop here, pick up elsewhere"),
        "nk_airdrop": ("AirDrop", "Sending and receiving with Apple devices"),
        "nk_notes": ("Notes", "The note pinned from HyprNotes, tickable here"),
        "nk_hover": ("Open on hover", "Without it, only Super+N opens the panel"),
        "nk_page": ("Default tab", "The one shown when it opens"),
        "g_input": ("Mouse and keyboard", "Input devices"),
        "sensitivity": ("Mouse sensitivity", "0 = raw sensor speed, no correction"),
        "natural_scroll": ("Natural scrolling", "Content follows your finger, like on a phone"),
        "accel": ("Pointer acceleration", "\"flat\" keeps a constant speed — better for precise aiming"),
        "kb_layout": ("Keyboard layout", "Set \"fr\" if your keys are AZERTY"),
        "g_waybar": ("Top bar", "Waybar — applied on save, the bar restarts"),
        "wb_height": ("Height", "0 = automatic, derived from the font size"),
        "wb_spacing": ("Module spacing", "Gap between two items in the bar"),
        "wb_margin_top": ("Top margin", "Distance between the bar and the screen edge"),
        "wb_margin_side": ("Side margins", "Inset on the left and right"),
        "wb_tray": ("System tray icon size", "This is what actually drives the bar thickness"),
        "wb_font_size": ("Text size", "As a percentage of the system font"),
        "wb_font_weight": ("Text weight", "400 = normal, 700 = bold — your font ships 8 levels"),
        "wb_pill_gap": ("Gap between bubbles", "Space separating two module groups"),
        "wb_pill_pad": ("Bubble height", "Padding above and below the content"),
        "wb_pill_padx": ("Bubble width", "Padding left and right of the content"),
    },
}

# (clé de traduction, chemin hyprland, min, max, pas, décimales)
LAYOUT = [
    ("g_spacing", [
        ("slider", "gaps_in", "general:gaps_in", 0, 40, 1, 0),
        ("slider", "gaps_out", "__gaps_side", 0, 80, 1, 0),
        ("slider", "gaps_top", "__gaps_top", 0, 80, 1, 0),
        ("slider", "border", "general:border_size", 0, 10, 1, 0),
    ]),
    ("g_deco", [
        ("slider", "rounding", "decoration:rounding", 0, 30, 1, 0),
        ("slider", "active_op", "decoration:active_opacity", 0.30, 1.0, 0.05, 2),
        ("slider", "inactive_op", "decoration:inactive_opacity", 0.30, 1.0, 0.05, 2),
    ]),
    ("g_blur", [
        ("switch", "blur_on", "decoration:blur:enabled"),
        ("slider", "blur_size", "decoration:blur:size", 1, 20, 1, 0),
        ("slider", "blur_passes", "decoration:blur:passes", 1, 4, 1, 0),
    ]),
    ("g_waybar", [
        ("slider", "wb_height", "waybar:height", 0, 60, 1, 0),
        ("slider", "wb_font_size", "waybar:font-size", 60, 120, 1, 0),
        ("slider", "wb_font_weight", "waybar:font-weight", 100, 800, 100, 0),
        ("slider", "wb_pill_gap", "waybar:pill-gap", 0, 20, 1, 0),
        ("slider", "wb_pill_pad", "waybar:pill-pad", 0, 12, 1, 0),
        ("slider", "wb_pill_padx", "waybar:pill-padx", 2, 30, 1, 0),
        ("slider", "wb_tray", "waybar:tray", 8, 28, 1, 0),
        ("slider", "wb_spacing", "waybar:spacing", 0, 20, 1, 0),
        ("slider", "wb_margin_top", "waybar:margin-top", 0, 24, 1, 0),
        ("slider", "wb_margin_side", "waybar:margin-side", 0, 40, 1, 0),
    ]),
    ("g_notch", [
        ("switch", "nk_media", "notch:widgets.media"),
        ("switch", "nk_calendar", "notch:widgets.calendar"),
        ("switch", "nk_system", "notch:widgets.system"),
        ("switch", "nk_files", "notch:widgets.files"),
        ("switch", "nk_airdrop", "notch:widgets.airdrop"),
        ("switch", "nk_notes", "notch:widgets.notes"),
        ("switch", "nk_hover", "notch:notch.hover_to_open"),
        ("combo", "nk_page", "notch:notch.default_page", NOTCH_PAGES),
    ]),
    ("g_input", [
        ("slider", "sensitivity", "input:sensitivity", -1.0, 1.0, 0.05, 2),
        ("switch", "natural_scroll", "input:touchpad:natural_scroll"),
        ("combo", "accel", "input:accel_profile", ["flat", "adaptive"]),
        ("combo", "kb_layout", "input:kb_layout", ["us", "fr"]),
    ]),
]



# --------------------------------------------------------------------------
# Langue : détection, persistance, drapeaux
# --------------------------------------------------------------------------

def has_emoji_font():
    """Les drapeaux ne s'affichent que si une police couvre les indicateurs régionaux."""
    try:
        result = subprocess.run(["fc-list", ":charset=1F1F7"],
                                capture_output=True, text=True, timeout=2)
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


EMOJI = has_emoji_font()
FLAGS = {"fr": ("\U0001F1EB\U0001F1F7", "Français"), "en": ("\U0001F1EC\U0001F1E7", "English")}


def flag_label(lang, with_name=False):
    emoji, name = FLAGS[lang]
    code = lang.upper()
    head = f"{emoji} {code}" if EMOJI else code
    return f"{head}  ·  {name}" if with_name else head


def load_lang():
    try:
        with open(LANG_FILE, encoding="utf-8") as handle:
            value = handle.read().strip()
            if value in T:
                return value
    except OSError:
        pass
    return "fr"


def save_lang(lang):
    try:
        with open(LANG_FILE, "w", encoding="utf-8") as handle:
            handle.write(lang)
    except OSError:
        pass


# Les composants qui lisent LANG_FILE une seule fois, a leur demarrage. Le
# fichier ne suffit donc pas : sans relance, changer la langue ici ne changeait
# que cette fenetre, et le notch restait dans l'ancienne jusqu'a la prochaine
# session - ce qui donne l'impression que le reglage ne marche pas.
LANG_CONSUMERS = (
    os.path.expanduser("~/.config/hypr/scripts/HyprNotch.py"),
    os.path.expanduser("~/.config/hypr/scripts/HyprWhale.py"),
)


def _pids_running(script):
    """PID des processus dont la ligne de commande contient ce chemin.

    On lit /proc plutot que d'appeler pkill : un motif assez large pour
    attraper "python .../HyprNotch.py" attrape aussi le shell qui le cherche,
    et se tue lui-meme. Ici on compare des chemins exacts, et on s'exclut.
    """
    me = os.getpid()
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == me:
            continue
        try:
            with open("/proc/%s/cmdline" % entry, "rb") as fh:
                args = fh.read().split(b"\0")
        except OSError:
            continue
        if any(arg.decode("utf-8", "replace") == script for arg in args):
            found.append(int(entry))
    return found


def restart_lang_consumers():
    """Relance ceux qui tournent, laisse dormir ceux qui ne tournent pas."""
    for script in LANG_CONSUMERS:
        pids = _pids_running(script)
        if not pids:
            continue
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        # Laisser la surface layer-shell se retirer avant d'en redemander une :
        # deux notchs qui se chevauchent une seconde, c'est visible.
        GLib.timeout_add(400, _respawn, script)


def _respawn(script):
    try:
        subprocess.Popen([script], start_new_session=True)
    except OSError:
        pass
    return False


# --------------------------------------------------------------------------
# Lecture / écriture du fichier de config (conscient des blocs imbriqués)
# --------------------------------------------------------------------------

def _walk(lines):
    stack = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        opening = re.match(r"^([A-Za-z_][\w-]*)\s*\{", stripped)
        if opening:
            stack.append(opening.group(1))
            continue
        if stripped.startswith("}"):
            if stack:
                stack.pop()
            continue
        assign = re.match(r"^([A-Za-z_][\w-]*)\s*=\s*(.+?)\s*(#.*)?$", stripped)
        if assign and stack:
            yield index, ":".join(stack + [assign.group(1)]), assign.group(2)


def read_conf():
    values = {}
    for source in (CONF, INPUT_CONF):
        try:
            with open(source, encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            continue
        values.update({path: value for _, path, value in _walk(lines)})
    values.update(read_waybar())
    values.update(read_notch())
    numbers = re.findall(r"[\d.]+", values.get("general:gaps_out", "10"))
    if numbers:
        values["__gaps_top"] = numbers[0]
        values["__gaps_side"] = numbers[1] if len(numbers) > 1 else numbers[0]
    return values


def write_conf(values):
    values = dict(values)
    write_waybar(values)
    write_notch(values)
    top = values.pop("__gaps_top", None)
    side = values.pop("__gaps_side", None)
    if top is not None and side is not None:
        values["general:gaps_out"] = f"{top},{side},{side},{side}"

    for source in (CONF, INPUT_CONF):
        try:
            with open(source, encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            continue

        touched = False
        for index, path, _ in list(_walk(lines)):
            if path not in values or file_for(path) != source:
                continue
            line = lines[index]
            indent = line[: len(line) - len(line.lstrip())]
            key = path.split(":")[-1]
            comment = re.search(r"(#.*)$", line.rstrip("\n"))
            suffix = f"  {comment.group(1)}" if comment else ""
            lines[index] = f"{indent}{key} = {values[path]}{suffix}\n"
            touched = True

        if touched:
            with open(source, "w", encoding="utf-8") as handle:
                handle.writelines(lines)


LUA_CONF = os.path.expanduser("~/.config/hypr/hyprland.lua")


def lua_parser():
    """Hyprland préfère hyprland.lua au .conf dès qu'il le trouve, et son
    parseur Lua refuse net `hyprctl keyword` : « keyword can't work with
    non-legacy parsers. Use eval. » Sans cette bascule, plus aucun curseur
    du panneau ne se voyait à l'écran."""
    return os.path.exists(LUA_CONF)


def _lua_scalar(value):
    text = str(value).strip().strip('"')
    if text in ("true", "false"):
        return text
    try:
        float(text)
    except ValueError:
        return '"%s"' % text.replace('"', '\\"')
    return text


def lua_config(path, value):
    """Traduit « decoration:blur:size = 8 » en la table imbriquée que
    `hl.config` attend."""
    if path.startswith("general:gaps"):
        # Type « css_gap » : le parseur Lua veut les quatre côtés nommés,
        # pas la chaîne « haut,droite,bas,gauche » héritée du .conf.
        sides = [part.strip() for part in str(value).split(",")]
        if len(sides) == 1:
            body = _lua_scalar(sides[0])
        else:
            while len(sides) < 4:
                sides.append(sides[-1])
            body = ("{ top = %s, right = %s, bottom = %s, left = %s }"
                    % tuple(sides[:4]))
    else:
        body = _lua_scalar(value)
    for key in reversed(path.split(":")):
        body = "{ %s = %s }" % (key, body)
    return "hl.config(%s)" % body


def apply_live(path, value):
    if lua_parser():
        subprocess.run(["hyprctl", "eval", lua_config(path, value)],
                       capture_output=True, check=False)
        return
    subprocess.run(["hyprctl", "keyword", path, str(value)],
                   capture_output=True, check=False)


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------

class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, default_width=580, default_height=760)

        self.lang = load_lang()
        self.values = read_conf()
        self.controls = {}
        self._pending = {}
        self._timer = None
        self._waybar_touched = False
        self._notch_touched = False

        self.toasts = Adw.ToastOverlay()

        self.header = Adw.HeaderBar()
        self.save_button = Gtk.Button()
        self.save_button.add_css_class("suggested-action")
        self.save_button.set_sensitive(False)
        self.save_button.connect("clicked", self.on_save)
        self.header.pack_end(self.save_button)

        self.lang_button = Gtk.MenuButton()
        self.lang_button.set_popover(self._make_lang_popover())
        self.header.pack_start(self.lang_button)

        self.revert_button = Gtk.Button(icon_name="edit-undo-symbolic")
        self.revert_button.connect("clicked", self.on_revert)
        self.header.pack_start(self.revert_button)

        self.scroller = Gtk.ScrolledWindow(vexpand=True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self.header)
        content.append(self.scroller)
        self.toasts.set_child(content)
        self.set_content(self.toasts)

        self.rebuild()

    # -- sélecteur de langue ----------------------------------------------

    def _make_lang_popover(self):
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        for code in ("fr", "en"):
            button = Gtk.Button(label=flag_label(code, with_name=True))
            button.add_css_class("flat")
            button.get_child().set_xalign(0.0)
            button.connect("clicked", self.on_lang_selected, code, popover)
            box.append(button)

        popover.set_child(box)
        return popover

    def on_lang_selected(self, _button, code, popover):
        popover.popdown()
        if code == self.lang:
            return
        self.lang = code
        save_lang(code)
        self.rebuild()
        restart_lang_consumers()

    # -- (re)construction --------------------------------------------------

    def rebuild(self):
        strings = T[self.lang]
        self.set_title(strings["window"])
        self.save_button.set_label(strings["save"])
        self.revert_button.set_tooltip_text(strings["reload"])
        self.lang_button.set_label(flag_label(self.lang))
        self.lang_button.set_tooltip_text(strings["lang_menu"])

        self.controls.clear()
        page = Adw.PreferencesPage()

        for group_key, rows in LAYOUT:
            title, description = strings[group_key]
            group = Adw.PreferencesGroup(title=title, description=description)
            for spec in rows:
                kind, rest = spec[0], spec[1:]
                if kind == "slider":
                    group.add(self._make_slider(*rest))
                elif kind == "switch":
                    group.add(self._make_switch(*rest))
                else:
                    group.add(self._make_combo(*rest))
            page.add(group)

        hint_title, hint_sub = strings["hint"]
        hint_group = Adw.PreferencesGroup()
        hint_row = Adw.ActionRow(title=hint_title, subtitle=hint_sub)
        hint_row.add_prefix(Gtk.Image.new_from_icon_name("emblem-important-symbolic"))
        hint_row.set_activatable(False)
        hint_group.add(hint_row)
        page.add(hint_group)

        self.scroller.set_child(page)

    def _make_slider(self, key, path, low, high, step, decimals):
        title, subtitle = T[self.lang][key]
        row = Adw.ActionRow(title=title, subtitle=subtitle)

        current = self._current(path, low)
        adjustment = Gtk.Adjustment(value=current, lower=low, upper=high,
                                    step_increment=step, page_increment=step)
        scale = Gtk.Scale(adjustment=adjustment, hexpand=False,
                          width_request=190, draw_value=False)
        scale.set_valign(Gtk.Align.CENTER)

        readout = Gtk.Label(label=self._format(current, decimals))
        readout.add_css_class("dim-label")
        readout.add_css_class("numeric")
        readout.set_width_chars(5)
        readout.set_xalign(1.0)

        def changed(widget):
            value = widget.get_value()
            value = round(value) if decimals == 0 else round(value / step) * step
            text = self._format(value, decimals)
            readout.set_label(text)
            self._queue(path, text)

        scale.connect("value-changed", changed)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.append(scale)
        box.append(readout)
        box.set_valign(Gtk.Align.CENTER)
        row.add_suffix(box)
        self.controls[path] = (adjustment, decimals)
        return row

    def _make_switch(self, key, path):
        title, subtitle = T[self.lang][key]
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        switch.set_active(self._truthy(self.values.get(path, "true")))
        switch.connect("notify::active",
                       lambda w, _: self._queue(path, "true" if w.get_active() else "false"))
        row.add_suffix(switch)
        row.set_activatable_widget(switch)
        self.controls[path] = (switch, None)
        return row

    def _make_combo(self, key, path, choices):
        title, subtitle = T[self.lang][key]
        model = Gtk.StringList.new(choices)
        row = Adw.ComboRow(title=title, subtitle=subtitle, model=model)

        current = str(self.values.get(path, choices[0])).strip().strip('"')
        row.set_selected(choices.index(current) if current in choices else 0)
        row.connect("notify::selected",
                    lambda r, _: self._queue(path, choices[r.get_selected()]))
        self.controls[path] = (row, choices)
        return row

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _truthy(value):
        return str(value).strip().lower() in ("true", "yes", "on", "1")

    def _current(self, path, fallback):
        try:
            return float(self.values.get(path))
        except (TypeError, ValueError):
            return float(fallback)

    @staticmethod
    def _format(value, decimals):
        return str(int(round(value))) if decimals == 0 else f"{value:.{decimals}f}"

    def _queue(self, path, value):
        if path.startswith("waybar:"):
            self._waybar_touched = True
        if path.startswith("notch:"):
            self._notch_touched = True
        self._pending[path] = value
        self.save_button.set_sensitive(True)
        if self._timer is None:
            self._timer = GLib.timeout_add(60, self._flush)

    def _flush(self):
        for path, value in self._pending.items():
            self.values[path] = value
            if path.startswith("waybar:") or path.startswith("notch:"):
                continue
            if path.startswith("__gaps"):
                top = self.values.get("__gaps_top", "10")
                side = self.values.get("__gaps_side", "10")
                apply_live("general:gaps_out", f"{top},{side},{side},{side}")
            else:
                apply_live(path, value)
        self._pending.clear()
        self._timer = None
        return GLib.SOURCE_REMOVE

    # -- actions -----------------------------------------------------------

    def on_save(self, _button):
        self._flush()
        write_conf(self.values)
        if self._waybar_touched:
            subprocess.Popen([os.path.expanduser("~/.config/hypr/scripts/wbrestart.sh")])
            self._waybar_touched = False
        if self._notch_touched:
            restart_notch()
            self._notch_touched = False
        self.save_button.set_sensitive(False)
        self.toasts.add_toast(Adw.Toast(title=T[self.lang]["saved"], timeout=2))

    def on_revert(self, _button):
        subprocess.run(["hyprctl", "reload"], capture_output=True, check=False)
        self.values = read_conf()
        for path, (widget, decimals) in self.controls.items():
            if isinstance(decimals, list):
                current = str(self.values.get(path, decimals[0])).strip().strip('"')
                widget.set_selected(decimals.index(current) if current in decimals else 0)
            elif decimals is None:
                widget.set_active(self._truthy(self.values.get(path, "true")))
            else:
                try:
                    widget.set_value(float(self.values.get(path, widget.get_value())))
                except (TypeError, ValueError):
                    pass
        self.save_button.set_sensitive(False)
        self.toasts.add_toast(Adw.Toast(title=T[self.lang]["reloaded"], timeout=2))


class HyprSettings(Adw.Application):
    def __init__(self):
        super().__init__(application_id="dev.local.HyprSettings")

    def do_activate(self):
        window = self.props.active_window or SettingsWindow(self)
        window.present()


if __name__ == "__main__":
    HyprSettings().run(None)
