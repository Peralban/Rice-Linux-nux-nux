"""Calendar widget: the current month, today highlighted, the next event.

Events come from an optional JSON file -- the notch imposes no calendar of its
own. The expected shape:

    [{"date": "2026-09-10", "title": "Weekly melo",
      "start": "10:00", "end": "11:00"}]
"""

import calendar
import datetime
import json
import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

EVENTS = os.path.expanduser("~/.config/hypr/scripts/.hyprnotch-events.json")

STRINGS = {
    "fr": {"none": "Aucun événement", "dow": ["L", "M", "M", "J", "V", "S", "D"],
           "months": ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
                      "Juil", "Août", "Sep", "Oct", "Nov", "Déc"],
           "prev": "Mois précédent", "next": "Mois suivant", "today": "Revenir à aujourd'hui"},
    "en": {"none": "No events", "dow": ["M", "T", "W", "T", "F", "S", "S"],
           "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
           "prev": "Previous month", "next": "Next month", "today": "Back to today"},
}


def load_events():
    try:
        with open(EVENTS, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {}
    out = {}
    for item in raw if isinstance(raw, list) else []:
        try:
            day = datetime.date.fromisoformat(item["date"])
        except (KeyError, TypeError, ValueError):
            continue
        out.setdefault(day, []).append({
            "title": str(item.get("title", "")),
            "start": str(item.get("start", "")),
            "end": str(item.get("end", "")),
        })
    return out


class CalendarWidget(Gtk.Box):
    def __init__(self, lang="fr"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.s = STRINGS.get(lang, STRINGS["fr"])
        self.today = datetime.date.today()
        self.shown = self.today.replace(day=1)
        self.events = {}

        header = Gtk.Box(spacing=6)
        self.month = Gtk.Label(xalign=0)
        self.month.add_css_class("nk-month")
        self.year = Gtk.Label(xalign=0, valign=Gtk.Align.BASELINE)
        self.year.add_css_class("nk-year")
        header.append(self.month)
        header.append(self.year)

        spacer = Gtk.Box(hexpand=True)
        header.append(spacer)
        header.append(self._nav("go-previous-symbolic", self.s["prev"], -1))
        header.append(self._nav("go-next-symbolic", self.s["next"], +1))
        self.append(header)

        self.grid = Gtk.Grid(column_homogeneous=True, row_spacing=1, column_spacing=1)
        self.append(self.grid)

        self.event_row = Gtk.Box(spacing=8)
        self.event_row.set_margin_top(2)
        self.bar = Gtk.Box()
        self.bar.add_css_class("nk-event-bar")
        self.bar.set_size_request(2, -1)
        self.event_name = Gtk.Label(xalign=0, ellipsize=3, hexpand=True)
        self.event_name.add_css_class("nk-event-name")
        self.event_time = Gtk.Label(xalign=1)
        self.event_time.add_css_class("nk-event-time")
        for widget in (self.bar, self.event_name, self.event_time):
            self.event_row.append(widget)
        self.append(self.event_row)

        self.refresh()

    def _nav(self, icon, tooltip, delta):
        button = Gtk.Button(tooltip_text=tooltip, valign=Gtk.Align.CENTER)
        button.set_child(Gtk.Image.new_from_icon_name(icon))
        button.add_css_class("nk-tab")
        button.connect("clicked", lambda *_: self._shift(delta))
        return button

    def _shift(self, delta):
        month = self.shown.month - 1 + delta
        year = self.shown.year + month // 12
        self.shown = datetime.date(year, month % 12 + 1, 1)
        self.refresh()

    def refresh(self):
        self.today = datetime.date.today()
        self.events = load_events()

        self.month.set_text(self.s["months"][self.shown.month - 1])
        self.year.set_text(str(self.shown.year))

        child = self.grid.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.grid.remove(child)
            child = nxt

        for column, name in enumerate(self.s["dow"]):
            label = Gtk.Label(label=name)
            label.add_css_class("nk-dow")
            self.grid.attach(label, column, 0, 1, 1)

        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(
            self.shown.year, self.shown.month)
        for row, week in enumerate(weeks, start=1):
            for column, day in enumerate(week):
                self.grid.attach(self._day(day), column, row, 1, 1)

        self._refresh_event()

    def _day(self, day):
        label = Gtk.Label(label=str(day.day))
        label.set_size_request(-1, 19)
        if day == self.today:
            label.add_css_class("nk-today")
        elif day.month != self.shown.month:
            label.add_css_class("nk-day-out")
        else:
            label.add_css_class("nk-day")
        if day in self.events:
            label.set_tooltip_text("\n".join(e["title"] for e in self.events[day]))
        return label

    def _refresh_event(self):
        upcoming = sorted(d for d in self.events if d >= self.today)
        if not upcoming:
            self.bar.set_visible(False)
            self.event_time.set_text("")
            self.event_name.set_text(self.s["none"])
            self.event_name.remove_css_class("nk-event-name")
            self.event_name.add_css_class("nk-empty")
            return
        day = upcoming[0]
        event = self.events[day][0]
        self.bar.set_visible(True)
        self.event_name.remove_css_class("nk-empty")
        self.event_name.add_css_class("nk-event-name")
        self.event_name.set_text(event["title"])
        span = " — ".join(v for v in (event["start"], event["end"]) if v)
        prefix = "" if day == self.today else f"{day.day}/{day.month} "
        self.event_time.set_text(prefix + span)
