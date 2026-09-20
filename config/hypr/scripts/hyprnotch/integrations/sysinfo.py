"""Reads the system's sensors, with no dependency and no subprocess.

Everything comes from /proc and /sys: no `nmcli`, `sensors` or `free` run in
a loop. The paths are resolved once, at startup.
"""

import glob
import os


def _read(path, default=""):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return default


def _int(path, default=0):
    try:
        return int(_read(path, ""))
    except ValueError:
        return default


def _find_temp():
    """Prefers the CPU's own sensor, falls back on the ACPI thermal zone."""
    for name in ("k10temp", "coretemp", "zenpower", "cpu_thermal"):
        for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
            if _read(os.path.join(hwmon, "name")) == name:
                for candidate in ("temp1_input", "temp2_input"):
                    path = os.path.join(hwmon, candidate)
                    if os.path.exists(path):
                        return path
    zones = sorted(glob.glob("/sys/class/thermal/thermal_zone*/temp"))
    return zones[0] if zones else None


def _find_battery():
    for path in sorted(glob.glob("/sys/class/power_supply/*")):
        if _read(os.path.join(path, "type")) == "Battery":
            return path
    return None


def _find_gpu():
    hits = sorted(glob.glob("/sys/class/drm/card*/device/gpu_busy_percent"))
    return hits[0] if hits else None


def _find_wifi():
    for path in sorted(glob.glob("/sys/class/net/*")):
        if os.path.exists(os.path.join(path, "wireless")):
            return path
    for path in sorted(glob.glob("/sys/class/net/*")):
        name = os.path.basename(path)
        if name != "lo" and not name.startswith(("docker", "veth", "br-")):
            return path
    return None


TEMP = _find_temp()
BATTERY = _find_battery()
GPU = _find_gpu()
NET = _find_wifi()


class Sampler:
    """CPU use is a delta: it needs two readings, spaced apart."""

    def __init__(self):
        self._last = self._cpu_jiffies()

    @staticmethod
    def _cpu_jiffies():
        line = _read("/proc/stat").split("\n")[0]
        parts = [int(v) for v in line.split()[1:] if v.isdigit()]
        if len(parts) < 4:
            return (0, 0)
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        return (sum(parts), idle)

    def cpu(self):
        total, idle = self._cpu_jiffies()
        prev_total, prev_idle = self._last
        self._last = (total, idle)
        d_total = total - prev_total
        d_idle = idle - prev_idle
        if d_total <= 0:
            return 0
        return max(0, min(100, round(100 * (d_total - d_idle) / d_total)))

    @staticmethod
    def memory():
        info = {}
        for line in _read("/proc/meminfo").split("\n"):
            key, _, rest = line.partition(":")
            value = rest.strip().split(" ")[0]
            if value.isdigit():
                info[key] = int(value)
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", 0)
        if not total:
            return 0, 0.0, 0.0
        used = total - available
        return round(100 * used / total), used / 1048576, total / 1048576

    @staticmethod
    def gpu():
        return _int(GPU, -1) if GPU else -1

    @staticmethod
    def temperature():
        if not TEMP:
            return -1
        raw = _int(TEMP, -1)
        return round(raw / 1000) if raw > 1000 else raw

    @staticmethod
    def battery():
        if not BATTERY:
            return None
        return {
            "percent": _int(os.path.join(BATTERY, "capacity"), 0),
            "status": _read(os.path.join(BATTERY, "status"), "Unknown"),
        }

    @staticmethod
    def network():
        if not NET:
            return {"name": "—", "up": False}
        name = os.path.basename(NET)
        state = _read(os.path.join(NET, "operstate"), "down")
        return {"name": name, "up": state == "up"}
