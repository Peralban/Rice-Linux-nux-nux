"""Notes tab: the pinned note, tickable from the notch.

Owns nothing. The note lives in ~/.local/share/hyprnotes/, HyprNotes writes to
the same directory, and the two watch each other: ticking here changes the
file, the window sees it and refreshes. The other way round too.

The panel is narrow -- this is a secondary view for a task list, not an editor.
But it is editable: typing here writes to disk.
"""

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

# The hyprnotes package sits next door, in ~/.config/hypr/scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from hyprnotes import markup  # noqa: E402
from hyprnotes.store import Store  # noqa: E402

SAVE_MS = 500

STRINGS = {
    "fr": {"title": "NOTES", "empty": "Aucune note épinglée",
           "hint": "Épingle-en une depuis HyprNotes", "untitled": "Sans titre"},
    "en": {"title": "NOTES", "empty": "No note pinned",
           "hint": "Pin one from HyprNotes", "untitled": "Untitled"},
}


class NotesWidget(Gtk.Box):
    def __init__(self, lang="fr", on_edit=None, on_arm=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.s = STRINGS.get(lang, STRINGS["fr"])
        # Tells the notch something is being typed: it has to pin itself, or
        # it closes on the first mouse movement and eats the keystroke.
        self.on_edit = on_edit
        # Tells the notch the pointer is over the text, so it opens the
        # keyboard before the click rather than during it.
        self.on_arm = on_arm
        self.store = Store()
        self.current = None
        self.dirty = False
        self.save_timer = None
        self.live = False

        header = Gtk.Box(spacing=6)
        label = Gtk.Label(label=self.s["title"], xalign=0)
        label.add_css_class("nk-sec")
        header.append(label)
        self.heading = Gtk.Label(xalign=1, hexpand=True, ellipsize=3)
        self.heading.add_css_class("nk-meta")
        header.append(self.heading)
        self.append(header)

        self.text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 left_margin=2, right_margin=2,
                                 top_margin=2, bottom_margin=2)
        self.text.add_css_class("nk-note")
        self.markup = markup.attach(self.text)
        self.text.get_buffer().connect("changed", self._on_typed)
        # Hovering the text arms the keyboard; the click pins and takes focus.
        # The two gestures are distinct because the compositor resolves a
        # click's fate under the mode in force before it: arming during the
        # click cost a second click.
        hover = Gtk.EventControllerMotion()
        hover.connect("enter", lambda *_: self._arm(True))
        # `motion` as much as `enter`: after giving the keyboard back the
        # pointer may have stayed over the text, and no enter event would ever
        # come again. `_set_kb` ignores repeats.
        hover.connect("motion", lambda *_: self._arm(True))
        hover.connect("leave", lambda *_: self._arm(False))
        self.text.add_controller(hover)

        # Capture phase, to run before the checkbox without stealing its
        # event.
        claim = Gtk.GestureClick()
        claim.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        claim.connect("pressed", self._on_click)
        self.text.add_controller(claim)

        scroll = Gtk.ScrolledWindow(vexpand=True,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.text)

        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3,
                             valign=Gtk.Align.CENTER, vexpand=True)
        title = Gtk.Label(label=self.s["empty"])
        title.add_css_class("nk-empty")
        hint = Gtk.Label(label=self.s["hint"], wrap=True, justify=2)
        hint.add_css_class("nk-meta")
        self.empty.append(title)
        self.empty.append(hint)

        self.stack = Gtk.Stack(vexpand=True)
        self.stack.add_named(scroll, "note")
        self.stack.add_named(self.empty, "empty")
        self.append(self.stack)

        self.store.watch(self._on_disk_change)
        self.refresh()

    # --- cycle de vie ---------------------------------------------------
    def set_live(self, live):
        """The tab becomes visible, or stops being so. We re-read on entry and
        write on exit: nothing is lost by closing the notch."""
        self.live = live
        if live:
            self.refresh()
        else:
            self.flush()

    def refresh(self):
        note_id = self.store.notch_note()
        if note_id is None:
            self.current = None
            self.heading.set_text("")
            self.stack.set_visible_child_name("empty")
            return

        note = self.store.read(note_id)
        if note is None:
            self.stack.set_visible_child_name("empty")
            return

        self.stack.set_visible_child_name("note")
        self.heading.set_text(note.title(self.s["untitled"]))
        if note_id == self.current and self.dirty:
            return
        buffer = self.text.get_buffer()
        if note_id == self.current and self.markup.serialize() == note.text:
            return
        offset = buffer.get_property("cursor-position") if note_id == self.current else 0
        self.current = note_id
        buffer.set_text(note.text)
        self.dirty = False
        self.markup.follow(self.text)
        self.markup.apply()
        buffer.place_cursor(buffer.get_iter_at_offset(
            min(offset, buffer.get_char_count())))

    # --- writing --------------------------------------------------------
    def _arm(self, on):
        if self.on_arm:
            self.on_arm(on)

    def _on_click(self, *_):
        if self.on_edit:
            self.on_edit()
        self.text.grab_focus()

    def _on_typed(self, _buffer):
        if self.current is None:
            return
        self.dirty = True
        if self.save_timer is not None:
            GLib.source_remove(self.save_timer)
        self.save_timer = GLib.timeout_add(SAVE_MS, self._save)

    def _save(self):
        self.save_timer = None
        self.flush()
        return False

    def flush(self):
        if not self.dirty or self.current is None:
            return
        self.store.write(self.current, self.markup.serialize())
        self.dirty = False
        self.heading.set_text(
            self.store.read(self.current).title(self.s["untitled"]))

    def _on_disk_change(self):
        # Hors panneau ouvert, inutile de redessiner : `set_live` relira.
        if self.live and not self.dirty:
            self.refresh()

    def reload_theme(self):
        self.markup.follow(self.text)
        self.markup.apply()
