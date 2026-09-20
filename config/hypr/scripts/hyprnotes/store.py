"""The note store: a directory of files, and nothing else.

A note is a `.md` file in ~/.local/share/hyprnotes/. No database, no
home-grown format: the notes stay greppable, editable in nvim, and they
outlive the application.

It is also the bus between the app and the notch. Both import this module and
watch the same directory: ticking a box in the notch moves a file, the app
sees it and refreshes. No daemon, no socket -- exactly the way the theme
already propagates in this repository.
"""

import json
import os
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

DIR = os.path.expanduser("~/.local/share/hyprnotes")

# Pins cannot live in the text without polluting it: a YAML header in a file
# we promise is "plain" would be a lie.
STATE = os.path.join(DIR, "state.json")

SUFFIX = ".md"

# Length of the preview shown under the title in the list.
PREVIEW = 80


def clean(line):
    """Strips a line's decoration to turn it into a readable title."""
    line = line.strip()
    line = line.lstrip("#").strip()
    for marker in ("- [ ]", "- [x]", "- [X]", "-", "*"):
        if line.startswith(marker):
            line = line[len(marker):].strip()
            break
    return line.replace("**", "")


class Note:
    """A note read from disk. Immutable: to write, go through the store, which
    knows how to invalidate its cache."""

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
        """The first line that carries anything, stripped of its decoration.
        There is no "title" field: the text is enough on its own."""
        for line in self.lines:
            cleaned = clean(line)
            if cleaned:
                return cleaned
        return fallback

    def preview(self):
        """The rest of the text, once the title is removed."""
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
    """Reads and writes notes, and reports when the directory changes."""

    def __init__(self):
        self.monitors = []
        self.listeners = []
        # What we have just written ourselves: the monitor will hand it back,
        # and refreshing on our own echo would make the caret jump mid-typing.
        self.echo = {}
        os.makedirs(DIR, exist_ok=True)

    # --- lecture --------------------------------------------------------
    def list(self):
        """Every note: pinned ones first, then the most recent."""
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

    # --- writing --------------------------------------------------------
    def write(self, note_id, text):
        path = self.path_of(note_id)
        try:
            # Atomic write: a half-written note, read by the notch at that
            # same instant, would display truncated.
            tmp = path + ".part"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)
            self.echo[path] = text
            return True
        except OSError:
            return False

    def create(self, text=""):
        """Creates a note and returns its identifier. The timestamp is enough:
        two notes created in the same second are told apart by a suffix."""
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

    # --- pins -----------------------------------------------------------
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
        """The notes kept at the top of the list. Several, with no limit."""
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
        """The note shown in the notch -- only one at a time."""
        note_id = self._state().get("notch")
        return note_id if self.exists(note_id) else None

    def set_notch_note(self, note_id):
        """Pinning to the notch replaces the previous one: the panel is narrow,
        two notes would not fit."""
        state = self._state()
        state["notch"] = None if state.get("notch") == note_id else note_id
        self._write_state(state)

    # --- veille ---------------------------------------------------------
    def watch(self, callback):
        """Calls `callback()` when the directory changes under our feet."""
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
        # Our own echo: the content on disk is what we just put there, nobody
        # else has spoken.
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
