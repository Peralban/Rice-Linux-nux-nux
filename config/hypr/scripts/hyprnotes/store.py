"""Le magasin de notes : un dossier de fichiers, et rien d'autre.

Une note est un fichier `.md` dans ~/.local/share/hyprnotes/. Pas de base
de données, pas de format maison : tes notes restent grepables, éditables
dans nvim, et elles survivent à l'application.

C'est aussi le bus entre l'app et le notch. Les deux importent ce module
et surveillent le même dossier : cocher une case dans le notch fait bouger
un fichier, l'app le voit et se rafraîchit. Aucun démon, aucun socket —
exactement comme le thème se propage déjà dans ce dépôt.
"""

import json
import os
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

DIR = os.path.expanduser("~/.local/share/hyprnotes")

# Les épingles ne peuvent pas vivre dans le texte sans le polluer : un
# en-tête YAML dans un fichier qu'on promet « brut » serait un mensonge.
STATE = os.path.join(DIR, "state.json")

SUFFIX = ".md"

# Longueur de l'aperçu affiché sous le titre dans la liste.
PREVIEW = 80


def clean(line):
    """Retire la décoration d'une ligne pour en faire un titre lisible."""
    line = line.strip()
    line = line.lstrip("#").strip()
    for marker in ("- [ ]", "- [x]", "- [X]", "-", "*"):
        if line.startswith(marker):
            line = line[len(marker):].strip()
            break
    return line.replace("**", "")


class Note:
    """Une note lue depuis le disque. Immuable : pour écrire, passe par le
    magasin, qui sait invalider son cache."""

    __slots__ = ("id", "path", "text", "mtime")

    def __init__(self, note_id, path, text, mtime):
        self.id = note_id
        self.path = path
        self.text = text
        self.mtime = mtime

    @property
    def lines(self):
        return self.text.splitlines()

    def title(self, fallback="Sans titre"):
        """La première ligne qui porte quelque chose, débarrassée de sa
        décoration. Pas de champ « titre » : le texte se suffit."""
        for line in self.lines:
            cleaned = clean(line)
            if cleaned:
                return cleaned
        return fallback

    def preview(self):
        """La suite du texte, une fois le titre retiré."""
        seen_title = False
        for line in self.lines:
            cleaned = clean(line)
            if not cleaned:
                continue
            if not seen_title:
                seen_title = True
                continue
            return cleaned[:PREVIEW]
        return ""

    @property
    def empty(self):
        return not self.text.strip()


class Store:
    """Lit et écrit les notes, et prévient quand le dossier bouge."""

    def __init__(self):
        self.monitors = []
        self.listeners = []
        # Ce qu'on vient d'écrire soi-même : le moniteur va nous le renvoyer,
        # et rafraîchir sur son propre écho ferait sauter le curseur en
        # pleine frappe.
        self.echo = {}
        os.makedirs(DIR, exist_ok=True)

    # --- lecture --------------------------------------------------------
    def list(self):
        """Toutes les notes : épinglées d'abord, puis les plus récentes."""
        notes = []
        try:
            names = os.listdir(DIR)
        except OSError:
            return notes
        for name in names:
            if not name.endswith(SUFFIX):
                continue
            note = self.read(name[: -len(SUFFIX)])
            if note is not None:
                notes.append(note)
        pinned = self.pinned()
        notes.sort(key=lambda n: (n.id not in pinned, -n.mtime))
        return notes

    def read(self, note_id):
        path = self.path_of(note_id)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            return Note(note_id, path, text, os.path.getmtime(path))
        except OSError:
            return None

    def path_of(self, note_id):
        return os.path.join(DIR, note_id + SUFFIX)

    def exists(self, note_id):
        return bool(note_id) and os.path.exists(self.path_of(note_id))

    # --- écriture -------------------------------------------------------
    def write(self, note_id, text):
        path = self.path_of(note_id)
        try:
            # Écriture atomique : une note à moitié écrite, lue par le notch
            # au même instant, s'afficherait tronquée.
            tmp = path + ".part"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)
            self.echo[path] = text
            return True
        except OSError:
            return False

    def create(self, text=""):
        """Crée une note et renvoie son identifiant. L'horodatage suffit :
        deux notes créées la même seconde sont départagées par un suffixe."""
        base = time.strftime("%Y%m%d-%H%M%S")
        note_id = base
        bump = 1
        while os.path.exists(self.path_of(note_id)):
            note_id = f"{base}-{bump}"
            bump += 1
        self.write(note_id, text)
        return note_id

    def delete(self, note_id):
        try:
            os.remove(self.path_of(note_id))
        except OSError:
            return False
        state = self._state()
        state["pinned"] = [i for i in state.get("pinned", []) if i != note_id]
        if state.get("notch") == note_id:
            state["notch"] = None
        self._write_state(state)
        return True

    # --- épingles -------------------------------------------------------
    def _state(self):
        try:
            with open(STATE, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        return {"pinned": [], "notch": None}

    def _write_state(self, state):
        try:
            tmp = STATE + ".part"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
                fh.write("\n")
            os.replace(tmp, STATE)
            self.echo[STATE] = json.dumps(state)
        except OSError:
            pass

    def pinned(self):
        """Les notes gardées en haut de la liste. Plusieurs, sans limite."""
        state = self._state()
        return [i for i in state.get("pinned", []) if isinstance(i, str)]

    def toggle_pin(self, note_id):
        state = self._state()
        pinned = [i for i in state.get("pinned", []) if isinstance(i, str)]
        if note_id in pinned:
            pinned.remove(note_id)
        else:
            pinned.insert(0, note_id)
        state["pinned"] = pinned
        self._write_state(state)

    def notch_note(self):
        """La note affichée dans le notch — une seule à la fois."""
        note_id = self._state().get("notch")
        return note_id if self.exists(note_id) else None

    def set_notch_note(self, note_id):
        """Épingler au notch remplace la précédente : le panneau est étroit,
        deux notes n'y tiendraient pas."""
        state = self._state()
        state["notch"] = None if state.get("notch") == note_id else note_id
        self._write_state(state)

    # --- veille ---------------------------------------------------------
    def watch(self, callback):
        """Appelle `callback()` quand le dossier change sous nos pieds."""
        self.listeners.append(callback)
        if self.monitors:
            return
        try:
            gfile = Gio.File.new_for_path(DIR)
            monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            monitor.connect("changed", self._on_event)
            self.monitors.append(monitor)
        except GLib.Error:
            pass

    def _on_event(self, _monitor, gfile, _other, event):
        if event not in (Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                         Gio.FileMonitorEvent.CREATED,
                         Gio.FileMonitorEvent.DELETED,
                         Gio.FileMonitorEvent.MOVED_IN,
                         Gio.FileMonitorEvent.RENAMED):
            return
        path = gfile.get_path() or ""
        if path.endswith(".part"):
            return
        # Notre propre écho : le contenu sur le disque est celui qu'on vient
        # d'y mettre, personne d'autre n'a parlé.
        if path in self.echo:
            try:
                with open(path, encoding="utf-8") as fh:
                    if fh.read() == self.echo[path]:
                        return
            except OSError:
                pass
            self.echo.pop(path, None)
        for callback in self.listeners:
            callback()
