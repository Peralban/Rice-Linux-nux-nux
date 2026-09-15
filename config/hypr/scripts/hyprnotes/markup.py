"""Mise en forme légère d'une note, dans la zone d'édition elle-même.

Le fichier reste du texte brut : on ne transforme rien, on habille. Les
marqueurs restent visibles mais grisés — les masquer dans une zone
éditable fait sauter le curseur de façon déroutante, puisqu'il traverse
alors des caractères qu'on ne voit pas.

Trois conventions, pas une de plus :
    # Titre        (jusqu'à ###)
    **gras**
    - [ ] tâche    et sa forme cochée - [x]

Le même module sert à l'app et à l'onglet du notch : la note a exactement
la même tête des deux côtés.
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

# Échelles des titres, relatives à la police de la note.
SCALE = {1: 1.45, 2: 1.20, 3: 1.06}

# Opacité des marqueurs (`#`, `**`, `- [ ]`) et du texte d'une tâche faite.
DIM = 0.42
DONE = 0.55


def _shade(rgba, alpha):
    out = Gdk.RGBA()
    out.red, out.green, out.blue = rgba.red, rgba.green, rgba.blue
    out.alpha = rgba.alpha * alpha
    return out


class Markup:
    """Habille un `Gtk.TextBuffer` et sait basculer ses cases à cocher."""

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
        """Reprend la couleur de texte effective du widget, et en tire les
        gris. Rien n'est écrit en dur : au changement de fond d'écran,
        matugen repeint GTK et les marqueurs suivent."""
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
        # `forward_chars` traverserait la fin de ligne : on borne d'abord.
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

    # --- cases à cocher -------------------------------------------------
    def checkbox_at(self, it):
        """Le numéro de ligne si `it` tombe sur une case, sinon None.
        Cliquer ailleurs sur la ligne ne coche rien : on veut pouvoir
        placer son curseur dans le texte d'une tâche."""
        line = it.get_line()
        text = self._text_of(line)
        found = TODO.match(text)
        if not found:
            return None
        offset = it.get_line_offset()
        # De `- [` à `]` inclus : la cible est petite mais franche.
        if found.start(2) <= offset <= found.end(4):
            return line
        return None

    def toggle(self, line):
        """Bascule `[ ]` et `[x]` sur place, sans toucher au reste."""
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
    """Branche le rendu sur une vue : habillage à chaque frappe, et clic
    sur une case pour la cocher. Renvoie le `Markup`."""
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
