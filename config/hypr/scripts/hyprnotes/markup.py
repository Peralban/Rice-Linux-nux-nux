"""Light formatting of a note, inside the editable view itself.

The file stays plain text: nothing is transformed, it is only dressed up. The
markers stay visible but greyed -- hiding them in an editable view makes the
caret jump in a disorienting way, since it then crosses characters nobody can
see.

Three conventions, not one more:
    # Heading      (up to ###)
    **bold**
    - [ ] task     and its ticked form - [x]
    ![](images/…)  a pasted image, shown in place of its line

The same module serves the app and the notch's tab: the note looks exactly the
same on both sides.
"""

import os
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from . import store  # noqa: E402

HEADING = re.compile(r"^(#{1,3})(\s+)(.*)$")
TODO = re.compile(r"^(\s*)(- \[)([ xX])(\])(\s?)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
BULLET = re.compile(r"^(\s*)([-*])(\s+)")
IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")

# An image is never shown taller than this, whatever its own size.
IMAGE_MAX = 320

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

    def __init__(self, buffer, view=None):
        self.buffer = buffer
        self.view = view
        # The marker each embedded image stands for, so the note can be saved
        # back as the plain text it has always been.
        self.anchors = {}
        self._busy = False
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

        self._images()

    # --- images ---------------------------------------------------------
    def _images(self):
        """Swaps each `![](…)` line for the picture it names. The marker is
        kept aside, and `serialize` puts it back: the file on disk stays the
        plain text it was."""
        if self.view is None or self._busy:
            return
        buffer = self.buffer
        pending = []
        for number in range(buffer.get_line_count()):
            text = self._text_of(number)
            found = IMAGE.match(text)
            if found:
                pending.append((number, text, found.group(2)))
        if not pending:
            return
        # Out of the `changed` emission: rewriting the buffer from inside its
        # own signal invalidates the iterators the emission is still holding.
        GLib.idle_add(self._embed_all, pending)

    def _embed_all(self, pending):
        for number, marker, target in pending:
            if IMAGE.match(self._text_of(number)):
                self._embed(number, marker, target)
        return GLib.SOURCE_REMOVE

    def _embed(self, number, marker, target):
        picture = self._picture(target)
        if picture is None:
            return
        buffer = self.buffer
        self._busy = True
        try:
            start = buffer.get_iter_at_line(number)[1]
            end = start.copy()
            if not end.ends_line():
                end.forward_to_line_end()
            # A mark, not an iterator: deleting the line invalidates every
            # iterator, and we still need that spot afterwards.
            spot = buffer.create_mark(None, start, True)
            buffer.delete(start, end)
            anchor = buffer.create_child_anchor(buffer.get_iter_at_mark(spot))
            buffer.delete_mark(spot)
            self.anchors[anchor] = marker
            self.view.add_child_at_anchor(picture, anchor)
            picture.show()
        finally:
            self._busy = False

    @staticmethod
    def _picture(target):
        path = target if os.path.isabs(target) else os.path.join(store.DIR, target)
        try:
            texture = Gdk.Texture.new_from_filename(path)
        except GLib.Error:
            return None
        picture = Gtk.Picture(paintable=texture)
        picture.set_can_shrink(True)
        picture.set_content_fit(Gtk.ContentFit.SCALE_DOWN)
        picture.set_halign(Gtk.Align.START)
        picture.set_margin_top(4)
        picture.set_margin_bottom(4)
        height = min(IMAGE_MAX, texture.get_height())
        width = round(texture.get_width() * height / max(1, texture.get_height()))
        picture.set_size_request(width, height)
        return picture

    def serialize(self):
        """The buffer as text, each embedded image back as its marker."""
        buffer = self.buffer
        start, end = buffer.get_bounds()
        raw = buffer.get_slice(start, end, True)
        if "\ufffc" not in raw:
            return raw
        out = []
        it = start.copy()
        for char in raw:
            if char == "\ufffc":
                anchor = it.get_child_anchor()
                out.append(self.anchors.get(anchor, "") if anchor else "")
            else:
                out.append(char)
            it.forward_char()
        return "".join(out)

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
    markup = Markup(buffer, view)

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

    keys = Gtk.EventControllerKey()
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)

    def on_key(_c, keyval, _code, state):
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if ctrl and keyval in (Gdk.KEY_v, Gdk.KEY_V) and paste_image(view):
            return Gdk.EVENT_STOP
        return Gdk.EVENT_PROPAGATE

    keys.connect("key-pressed", on_key)
    view.add_controller(keys)
    return markup


def paste_image(view):
    """A screenshot in the clipboard lands in the note as a file plus its
    marker. Anything else is left to the usual paste."""
    clipboard = view.get_clipboard()
    formats = clipboard.get_formats()
    # On Wayland the offer's type list arrives with the keyboard focus, so it
    # is briefly empty in a window that has not been focused yet. Empty is not
    # "no image": claim nothing then, and let the ordinary paste happen.
    if not (formats.contain_gtype(Gdk.Texture.__gtype__)
            or formats.contain_mime_type("image/png")):
        return False
    buffer = view.get_buffer()

    def done(source, result):
        try:
            texture = source.read_texture_finish(result)
        except GLib.Error:
            return
        if texture is None:
            return
        path = store.new_image()
        texture.save_to_png(path)
        it = buffer.get_iter_at_mark(buffer.get_insert())
        head = "" if it.starts_line() else "\n"
        buffer.insert(it, f"{head}![image]({os.path.relpath(path, store.DIR)})\n")

    clipboard.read_texture_async(None, done)
    return True
