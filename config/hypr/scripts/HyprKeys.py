#!/usr/bin/env python3
"""Éditeur graphique des raccourcis Hyprland (bilingue FR / EN).

Lit et réécrit ~/.config/hypr/configs/keybinds.conf en préservant
commentaires, ordre et mise en forme du fichier.
"""

import os
import re
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

CONF = os.path.expanduser("~/.config/hypr/configs/keybinds.conf")
MAIN = os.path.expanduser("~/.config/hypr/hyprland.conf")
LANG_FILE = os.path.expanduser("~/.config/hypr/scripts/.hyprkeys-lang")

BIND_RE = re.compile(r"^(bind[a-z]*)\s*=\s*(.*)$")

T = {
    "fr": {
        "window": "Raccourcis Hyprland",
        "search": "Rechercher un raccourci…",
        "add": "Nouveau raccourci",
        "save": "Enregistrer",
        "saved": "Enregistré — Hyprland a rechargé",
        "edit_title": "Modifier le raccourci",
        "new_title": "Nouveau raccourci",
        "combo": "Combinaison",
        "capture": "Appuie sur les touches…",
        "capture_hint": "Clique ici puis appuie sur la combinaison voulue",
        "action": "Action",
        "action_hint": "Ex : exec, kitty   ou   killactive",
        "cancel": "Annuler",
        "apply": "Valider",
        "delete": "Supprimer",
        "delete_q": "Supprimer ce raccourci ?",
        "delete_body": "Il sera retiré du fichier au prochain enregistrement.",
        "unsaved": "Modifications non enregistrées",
        "count": "{n} raccourcis",
        "lang_menu": "Langue",
        "empty": "Aucun raccourci ne correspond",
    },
    "en": {
        "window": "Hyprland Shortcuts",
        "search": "Search a shortcut…",
        "add": "New shortcut",
        "save": "Save",
        "saved": "Saved — Hyprland reloaded",
        "edit_title": "Edit shortcut",
        "new_title": "New shortcut",
        "combo": "Key combination",
        "capture": "Press your keys…",
        "capture_hint": "Click here, then press the combination you want",
        "action": "Action",
        "action_hint": "e.g. exec, kitty   or   killactive",
        "cancel": "Cancel",
        "apply": "Apply",
        "delete": "Delete",
        "delete_q": "Delete this shortcut?",
        "delete_body": "It will be removed from the file on next save.",
        "unsaved": "Unsaved changes",
        "count": "{n} shortcuts",
        "lang_menu": "Language",
        "empty": "No shortcut matches",
    },
}

FLAGS = {"fr": ("\U0001F1EB\U0001F1F7", "Français"), "en": ("\U0001F1EC\U0001F1E7", "English")}


def has_emoji_font():
    try:
        result = subprocess.run(["fc-list", ":charset=1F1F7"],
                                capture_output=True, text=True, timeout=2)
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


EMOJI = has_emoji_font()


def flag_label(lang, with_name=False):
    emoji, name = FLAGS[lang]
    head = f"{emoji} {lang.upper()}" if EMOJI else lang.upper()
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


# --------------------------------------------------------------------------
# Modèle : lecture / écriture du fichier
# --------------------------------------------------------------------------

class Bind:
    __slots__ = ("index", "kind", "mods", "key", "action", "comment", "deleted", "added")

    def __init__(self, index, kind, mods, key, action, comment):
        self.index = index          # ligne d'origine, ou None si ajouté
        self.kind = kind            # bind, binde, bindm, bindl, bindel
        self.mods = mods            # "$mainMod SHIFT"
        self.key = key              # "Return"
        self.action = action        # "exec, kitty"
        self.comment = comment      # "# ..." ou ""
        self.deleted = False
        self.added = index is None

    def combo(self, main_mod):
        mods = self.mods.replace("$mainMod", main_mod).strip()
        parts = [p for p in mods.split() if p]
        parts.append(self.key)
        return " + ".join(parts)

    def to_line(self):
        left = f"{self.mods}, {self.key}" if self.mods else f", {self.key}"
        suffix = f" {self.comment}" if self.comment else ""
        return f"{self.kind} = {left}, {self.action}{suffix}\n"


def main_mod_value():
    try:
        with open(CONF, encoding="utf-8") as handle:
            for line in handle:
                if line.strip().startswith("$mainMod"):
                    return line.split("=", 1)[1].split("#")[0].strip()
    except OSError:
        pass
    return "SUPER"


def read_binds():
    try:
        with open(CONF, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return [], []

    binds = []
    for index, line in enumerate(lines):
        match = BIND_RE.match(line.strip())
        if not match:
            continue
        kind, body = match.group(1), match.group(2)

        comment = ""
        hash_pos = body.find("#")
        if hash_pos != -1:
            comment = body[hash_pos:].strip()
            body = body[:hash_pos]

        parts = body.split(",")
        if len(parts) < 3:
            continue
        mods = parts[0].strip()
        key = parts[1].strip()
        action = ",".join(parts[2:]).strip().rstrip(",")
        binds.append(Bind(index, kind, mods, key, action, comment))
    return binds, lines


def write_binds(binds, lines):
    lines = list(lines)

    for bind in binds:
        if bind.index is None or bind.deleted:
            continue
        indent = re.match(r"^\s*", lines[bind.index]).group(0)
        lines[bind.index] = indent + bind.to_line()

    for bind in sorted((b for b in binds if b.deleted and b.index is not None),
                       key=lambda b: b.index, reverse=True):
        del lines[bind.index]

    fresh = [b for b in binds if b.index is None and not b.deleted]
    if fresh:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append("\n# === Ajouts via HyprKeys ===\n")
        lines.extend(b.to_line() for b in fresh)

    with open(CONF, "w", encoding="utf-8") as handle:
        handle.writelines(lines)


# --------------------------------------------------------------------------
# Capture de touches
# --------------------------------------------------------------------------

MOD_ORDER = [
    (Gdk.ModifierType.SUPER_MASK, "SUPER"),
    (Gdk.ModifierType.CONTROL_MASK, "CTRL"),
    (Gdk.ModifierType.ALT_MASK, "ALT"),
    (Gdk.ModifierType.SHIFT_MASK, "SHIFT"),
]

BARE_MODIFIERS = {
    "Super_L", "Super_R", "Control_L", "Control_R",
    "Alt_L", "Alt_R", "Shift_L", "Shift_R", "ISO_Level3_Shift",
}


def keyval_to_hypr(keyval):
    name = Gdk.keyval_name(keyval) or ""
    if len(name) == 1 and name.isalpha():
        return name.upper()
    return name


class ComboCapture(Gtk.Button):
    """Bouton qui enregistre la prochaine combinaison de touches pressée."""

    def __init__(self, mods, key, on_change):
        super().__init__()
        self.mods = mods
        self.key = key
        self.on_change = on_change
        self.listening = False

        self.set_has_frame(True)
        self.add_css_class("pill")
        self.connect("clicked", self._start)

        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self._on_key)
        self.add_controller(controller)

        self._refresh()

    def _label(self):
        mods = self.mods.replace("$mainMod", "SUPER").split()
        parts = mods + ([self.key] if self.key else [])
        return " + ".join(parts) if parts else "—"

    def _refresh(self, text=None):
        self.set_label(text if text is not None else self._label())

    def _start(self, _button):
        self.listening = True
        self._refresh(T[self.get_root().lang]["capture"])
        self.grab_focus()

    def _on_key(self, _controller, keyval, _keycode, state):
        if not self.listening:
            return Gdk.EVENT_PROPAGATE

        name = Gdk.keyval_name(keyval) or ""
        if name in BARE_MODIFIERS:
            return Gdk.EVENT_STOP  # on attend une vraie touche

        if name == "Escape":
            self.listening = False
            self._refresh()
            return Gdk.EVENT_STOP

        mods = [label for mask, label in MOD_ORDER if state & mask]
        # on garde le style du fichier : $mainMod plutot que SUPER
        mods = ["$mainMod" if m == "SUPER" else m for m in mods]

        self.mods = " ".join(mods)
        self.key = keyval_to_hypr(keyval)
        self.listening = False
        self._refresh()
        self.on_change()
        return Gdk.EVENT_STOP


# --------------------------------------------------------------------------
# Boîte d'édition
# --------------------------------------------------------------------------

class EditDialog(Adw.Dialog):
    def __init__(self, window, bind, is_new):
        super().__init__()
        self.window = window
        self.bind = bind
        self.is_new = is_new
        strings = T[window.lang]

        self.set_content_width(460)
        self.set_title(strings["new_title"] if is_new else strings["edit_title"])

        header = Adw.HeaderBar()
        cancel = Gtk.Button(label=strings["cancel"])
        cancel.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel)

        apply_button = Gtk.Button(label=strings["apply"])
        apply_button.add_css_class("suggested-action")
        apply_button.connect("clicked", self._on_apply)
        header.pack_end(apply_button)

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup()

        combo_row = Adw.ActionRow(title=strings["combo"], subtitle=strings["capture_hint"])
        self.capture = ComboCapture(bind.mods, bind.key, lambda: None)
        self.capture.set_valign(Gtk.Align.CENTER)
        combo_row.add_suffix(self.capture)
        group.add(combo_row)

        self.action_row = Adw.EntryRow(title=strings["action"])
        self.action_row.set_text(bind.action)
        group.add(self.action_row)

        hint = Adw.ActionRow(subtitle=strings["action_hint"])
        hint.set_activatable(False)
        group.add(hint)
        page.add(group)

        if not is_new:
            danger = Adw.PreferencesGroup()
            delete = Gtk.Button(label=strings["delete"])
            delete.add_css_class("destructive-action")
            delete.set_margin_top(6)
            delete.connect("clicked", self._on_delete)
            danger.add(delete)
            page.add(danger)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        box.append(page)
        self.set_child(box)

    def _on_apply(self, _button):
        if not self.capture.key:
            return
        self.bind.mods = self.capture.mods
        self.bind.key = self.capture.key
        self.bind.action = self.action_row.get_text().strip()
        if self.is_new:
            self.window.binds.append(self.bind)
        self.window.mark_dirty()
        self.window.refresh_list()
        self.close()

    def _on_delete(self, _button):
        self.bind.deleted = True
        self.window.mark_dirty()
        self.window.refresh_list()
        self.close()


# --------------------------------------------------------------------------
# Fenêtre principale
# --------------------------------------------------------------------------

class KeysWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, default_width=680, default_height=780)

        self.lang = load_lang()
        self.binds, self.lines = read_binds()
        self.main_mod = main_mod_value()
        self.dirty = False

        self.toasts = Adw.ToastOverlay()

        self.header = Adw.HeaderBar()
        self.lang_button = Gtk.MenuButton()
        self.lang_button.set_popover(self._lang_popover())
        self.header.pack_start(self.lang_button)

        self.add_button = Gtk.Button(icon_name="list-add-symbolic")
        self.add_button.connect("clicked", self._on_add)
        self.header.pack_start(self.add_button)

        self.save_button = Gtk.Button()
        self.save_button.add_css_class("suggested-action")
        self.save_button.set_sensitive(False)
        self.save_button.connect("clicked", self._on_save)
        self.header.pack_end(self.save_button)

        self.search = Gtk.SearchEntry(hexpand=True)
        self.search.connect("search-changed", lambda *_: self.listbox.invalidate_filter())
        search_bar = Gtk.Box(margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        search_bar.append(self.search)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.listbox.set_filter_func(self._filter)
        self.listbox.set_margin_start(12)
        self.listbox.set_margin_end(12)
        self.listbox.set_margin_bottom(12)

        scroller = Gtk.ScrolledWindow(child=self.listbox, vexpand=True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self.header)
        content.append(search_bar)
        content.append(scroller)
        self.toasts.set_child(content)
        self.set_content(self.toasts)

        self.retranslate()
        self.refresh_list()

    # -- langue ------------------------------------------------------------

    def _lang_popover(self):
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                      margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        for code in ("fr", "en"):
            button = Gtk.Button(label=flag_label(code, with_name=True))
            button.add_css_class("flat")
            button.get_child().set_xalign(0.0)
            button.connect("clicked", self._on_lang, code, popover)
            box.append(button)
        popover.set_child(box)
        return popover

    def _on_lang(self, _button, code, popover):
        popover.popdown()
        if code == self.lang:
            return
        self.lang = code
        save_lang(code)
        self.retranslate()
        self.refresh_list()

    def retranslate(self):
        strings = T[self.lang]
        self.set_title(strings["window"])
        self.search.set_placeholder_text(strings["search"])
        self.save_button.set_label(strings["save"])
        self.add_button.set_tooltip_text(strings["add"])
        self.lang_button.set_label(flag_label(self.lang))
        self.lang_button.set_tooltip_text(strings["lang_menu"])

    # -- liste -------------------------------------------------------------

    def refresh_list(self):
        while (child := self.listbox.get_first_child()) is not None:
            self.listbox.remove(child)

        for bind in self.binds:
            if bind.deleted:
                continue
            row = Adw.ActionRow(title=GLib.markup_escape_text(bind.combo(self.main_mod)),
                                subtitle=GLib.markup_escape_text(bind.action))
            row.set_activatable(True)
            row.connect("activated", self._on_edit, bind)
            row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            if bind.added:
                badge = Gtk.Label(label="•")
                badge.add_css_class("accent")
                row.add_prefix(badge)
            self.listbox.append(row)

    def _filter(self, row):
        text = self.search.get_text().strip().lower()
        if not text:
            return True
        title = (row.get_title() or "").lower()
        subtitle = (row.get_subtitle() or "").lower()
        return text in title or text in subtitle

    # -- actions -----------------------------------------------------------

    def _on_edit(self, _row, bind):
        EditDialog(self, bind, is_new=False).present(self)

    def _on_add(self, _button):
        bind = Bind(None, "bind", "$mainMod", "", "exec, ", "")
        EditDialog(self, bind, is_new=True).present(self)

    def mark_dirty(self):
        self.dirty = True
        self.save_button.set_sensitive(True)

    def _on_save(self, _button):
        write_binds(self.binds, self.lines)
        subprocess.run(["hyprctl", "reload"], capture_output=True, check=False)
        self.binds, self.lines = read_binds()
        self.main_mod = main_mod_value()
        self.dirty = False
        self.save_button.set_sensitive(False)
        self.refresh_list()
        self.toasts.add_toast(Adw.Toast(title=T[self.lang]["saved"], timeout=2))


class HyprKeys(Adw.Application):
    def __init__(self):
        super().__init__(application_id="dev.local.HyprKeys")

    def do_activate(self):
        window = self.props.active_window or KeysWindow(self)
        window.present()


if __name__ == "__main__":
    HyprKeys().run(None)
