"""Light formatting of a note, inside the editable view itself.

The file stays plain text: nothing is transformed, it is only dressed up. The
markers stay visible but greyed -- hiding them in an editable view makes the
caret jump in a disorienting way, since it then crosses characters nobody can
see.

Three conventions, not one more:
    # Heading      (up to ###)
    **bold**
    - [ ] task     and its ticked form - [x]

The same module serves the app and the notch's tab: the note looks exactly the
same on both sides.
"""

import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk, Pango  # noqa: E402

HEADING = re.compile(r"^(#{1,3})(\s+)(.*)$")
TODO = re.compile(r"^(\s*)(- \[)([ xX])(\])(\s?)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
BULLET = re.compile(r"^(\s*)([-*])(\s+)")

# Heading scales, relative to the note's font.
SCALE = {1: 1.45, 2: 1.20, 3: 1.06}

# Opacity of the markers (`#`, `**`, `- [ ]`) and of a done task's text.
DIM = 0.42
DONE = 0.55


def _shade(rgba, alpha):
    out = Gdk.RGBA()
    out.red, out.green, out.blue = rgba.red, rgba.green, rgba.blue
    out.alpha = rgba.alpha * alpha
    return out


class Markup:
    """Dresses up a `Gtk.TextBuffer` and knows how to toggle its checkboxes."""

    def __init__(self, buffer):
        self.buffer = buffer
        self.tags = {}
        table = buffer.get_tag_table()

        def tag(name, **props):
            existing = table.lookup(name)
            if existing is not None:
                self.tags[name] = existing
                return
            self.tags[name] = buffer.create_tag(name, **props)

        for level, scale in SCALE.items():
            tag(f"h{level}", scale=scale, weight=Pango.Weight.BOLD,
                pixels_above_lines=8, pixels_below_lines=2)
        tag("bold", weight=Pango.Weight.BOLD)
        tag("marker")
        tag("done", strikethrough=True)
        tag("box", weight=Pango.Weight.BOLD)

    # --- couleurs -------------------------------------------------------
    def follow(self, widget):
        """Takes the widget's effective text colour and derives the greys from
        it. Nothing is hard-coded: on a wallpaper change matugen repaints GTK
        and the markers follow."""
        base = widget.get_color()
        self.tags["marker"].props.foreground_rgba = _shade(base, DIM)
        self.tags["done"].props.foreground_rgba = _shade(base, DONE)

    # --- habillage ------------------------------------------------------
    def apply(self):
        buffer = self.buffer
        start, end = buffer.get_bounds()
        for name in self.tags:
            buffer.remove_tag_by_name(name, start, end)

        for number in range(buffer.get_line_count()):
            line_start = buffer.get_iter_at_line(number)[1]
            line_end = line_start.copy()
            if not line_end.ends_line():
                line_end.forward_to_line_end()
            text = buffer.get_text(line_start, line_end, False)
            self._line(number, text)

    def _iter(self, line, offset):
        it = self.buffer.get_iter_at_line(line)[1]
        # `forward_chars` would cross the line end: bound it first.
        limit = it.copy()
        if not limit.ends_line():
            limit.forward_to_line_end()
        it.forward_chars(min(offset, limit.get_line_offset()))
        return it

    def _tag(self, name, line, start, end):
        if end <= start:
            return
        self.buffer.apply_tag(self.tags[name], self._iter(line, start),
                              self._iter(line, end))

    def _line(self, number, text):
        body_from = 0

        heading = HEADING.match(text)
        if heading:
            level = len(heading.group(1))
            body_from = heading.end(2)
            self._tag(f"h{level}", number, 0, len(text))
            self._tag("marker", number, 0, body_from)
            self._bold(number, text, body_from)
            return

        todo = TODO.match(text)
        if todo:
            body_from = todo.end()
            self._tag("marker", number, todo.start(2), todo.start(3))
            self._tag("box", number, todo.start(3), todo.end(3))
            self._tag("marker", number, todo.end(3), todo.end(4))
            if todo.group(3) in ("x", "X"):
                self._tag("done", number, body_from, len(text))
            self._bold(number, text, body_from)
            return

        bullet = BULLET.match(text)
        if bullet:
            body_from = bullet.end()
            self._tag("marker", number, bullet.start(2), bullet.end(2))

        self._bold(number, text, body_from)

    def _bold(self, number, text, offset):
        for found in BOLD.finditer(text, offset):
            self._tag("marker", number, found.start(), found.start() + 2)
            self._tag("bold", number, found.start() + 2, found.end() - 2)
            self._tag("marker", number, found.end() - 2, found.end())

    # --- checkboxes -----------------------------------------------------
    def checkbox_at(self, it):
        """The line number if `it` lands on a box, otherwise None. Clicking
        elsewhere on the line ticks nothing: the caret has to be placeable
        inside a task's text."""
        line = it.get_line()
        text = self._text_of(line)
        found = TODO.match(text)
        if not found:
            return None
        offset = it.get_line_offset()
        # From `- [` through `]` inclusive: a small but unambiguous target.
        if found.start(2) <= offset <= found.end(4):
            return line
        return None

    def toggle(self, line):
        """Toggles `[ ]` and `[x]` in place, touching nothing else."""
        text = self._text_of(line)
        found = TODO.match(text)
        if not found:
            return False
        mark = "x" if found.group(3) == " " else " "
        start = self._iter(line, found.start(3))
        end = self._iter(line, found.end(3))
        self.buffer.delete(start, end)
        self.buffer.insert(start, mark)
        return True

    def _text_of(self, line):
        start = self.buffer.get_iter_at_line(line)[1]
        end = start.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        return self.buffer.get_text(start, end, False)


def attach(view):
    """Wires the rendering to a view: dress up on every keystroke, and a click
    on a box to tick it. Returns the `Markup`."""
    buffer = view.get_buffer()
    markup = Markup(buffer)

    def restyle(*_):
        markup.apply()
        return False

    buffer.connect("changed", restyle)

    click = Gtk.GestureClick()

    def on_release(gesture, n_press, x, y):
        if n_press != 1:
            return
        bx, by = view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        ok, it = view.get_iter_at_location(bx, by)
        if not ok:
            return
        line = markup.checkbox_at(it)
        if line is not None:
            markup.toggle(line)
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    click.connect("released", on_release)
    view.add_controller(click)
    return markup
