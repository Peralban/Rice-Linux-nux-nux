"""System widget: CPU, RAM, GPU, temperature, battery, network.

Measures nothing while the panel is closed.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from ..integrations.sysinfo import Sampler

TICK_MS = 2000

STRINGS = {
    "fr": {"cpu": "CPU", "ram": "RAM", "gpu": "GPU", "temp": "TEMP"},
    "en": {"cpu": "CPU", "ram": "RAM", "gpu": "GPU", "temp": "TEMP"},
}


class Gauge(Gtk.Box):
    def __init__(self, key):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row = Gtk.Box()
        self.key = Gtk.Label(label=key, xalign=0, hexpand=True)
        self.key.add_css_class("nk-stat-key")
        self.value = Gtk.Label(xalign=1)
        self.value.add_css_class("nk-stat-val")
        row.append(self.key)
        row.append(self.value)
        self.append(row)
        self.bar = Gtk.ProgressBar()
        self.bar.add_css_class("nk-gauge")
        self.append(self.bar)

    def set(self, text, fraction=None):
        self.value.set_text(text)
        self.bar.set_visible(fraction is not None)
        if fraction is not None:
            self.bar.set_fraction(max(0.0, min(1.0, fraction)))


class SystemWidget(Gtk.Box):
    def __init__(self, lang="fr"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=9,
                         valign=Gtk.Align.CENTER)
        self.s = STRINGS.get(lang, STRINGS["fr"])
        self.sampler = Sampler()
        self.tick = None

        self.cpu = Gauge(self.s["cpu"])
        self.ram = Gauge(self.s["ram"])
        self.gpu = Gauge(self.s["gpu"])
        for gauge in (self.cpu, self.ram, self.gpu):
            self.append(gauge)

        self.temp = Gtk.Label(halign=Gtk.Align.CENTER)
        self.temp.add_css_class("nk-meta")
        self.append(self.temp)

    def set_live(self, live):
        if live and self.tick is None:
            self.tick = GLib.timeout_add(TICK_MS, self._on_tick)
            self.refresh()
        elif not live and self.tick is not None:
            GLib.source_remove(self.tick)
            self.tick = None

    def _on_tick(self):
        if self.tick is None:
            return False
        self.refresh()
        return True

    def refresh(self):
        cpu = self.sampler.cpu()
        self.cpu.set(f"{cpu}%", cpu / 100)

        percent, used, total = self.sampler.memory()
        self.ram.set(f"{percent}%  ·  {used:.1f}/{total:.0f} Go", percent / 100)

        gpu = self.sampler.gpu()
        if gpu >= 0:
            self.gpu.set(f"{gpu}%", gpu / 100)
            self.gpu.set_visible(True)
        else:
            self.gpu.set_visible(False)

        temperature = self.sampler.temperature()
        self.temp.set_text(f"{self.s['temp']}  {temperature}°C" if temperature >= 0 else "")
