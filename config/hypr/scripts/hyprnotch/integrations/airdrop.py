"""Bridge to `airdropd`, the AirDrop daemon from the airdrop-mt7921 project.

Everything goes through the daemon's binary: it alone knows how to talk to the
privileged wrapper, and it alone holds the lock that keeps two toggles from
racing during the ~20 s the radio takes to come up.

Nothing is queried while the page is not visible: `set_live()` follows the same
discipline as the system widget.
"""

import json
import os
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

HOME = os.path.expanduser("~")
DAEMON = os.path.join(HOME, ".local/share/airdrop-mt7921/daemon/airdropd")
SENDER = os.path.join(HOME, ".local/share/airdrop-mt7921/daemon/airdrop-send")

# What the upstream project's bar exports too: the switch has to mean "you can
# be dropped on right now", with no BLE step and without giving up the Wi-Fi
# association -- that is always-on plus P2P-GO.
ENV = {"AIRDROP_ALWAYS": "1", "AIRDROP_DUALCHAN": "1"}

STATE_FILE = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "airdropd", "state.json")

# The states the daemon publishes, and what they mean to the user. "on" covers
# more than `armed`: during bring-up and during a send the radio IS on, and
# showing "off" there reads as though the toggle had failed.
ON_STATES = ("idle", "waking", "armed", "switching", "unreachable", "sending")


def _environ():
    env = dict(os.environ)
    env.update(ENV)
    return ["%s=%s" % kv for kv in env.items()]


def _spawn(argv, done=None):
    """Runs a command without blocking the GTK loop."""
    try:
        proc = Gio.Subprocess.new(
            argv,
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)
    except GLib.Error:
        if done is not None:
            done(None)
        return

    def finished(p, result):
        try:
            _, out, _ = p.communicate_utf8_finish(result)
        except GLib.Error:
            out = None
        if done is not None:
            done(out)

    proc.communicate_utf8_async(None, None, finished)


def available():
    return os.access(DAEMON, os.X_OK)


def nudge(state, detail=""):
    """An optimistic state, written by the click rather than by the daemon.

    Turning the radio on takes some twenty seconds. Without this the switch
    keeps its old label for several polls after the click, which makes it look
    broken -- and so gets clicked again, which is exactly the race the daemon's
    lock exists to prevent.
    """
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as handle:
            json.dump({"state": state, "detail": detail, "ts": int(time.time())}, handle)
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass


class AirDrop:
    def __init__(self, config=None):
        self.state = "off"
        self.detail = ""
        self._listeners = []

    def connect(self, callback):
        self._listeners.append(callback)

    def _emit(self):
        for callback in self._listeners:
            callback(self.state, self.detail)

    # --- reading --------------------------------------------------------
    def refresh(self):
        if not available():
            self._set("missing", "")
            return
        _spawn([DAEMON, "status"], self._on_status)

    def _on_status(self, out):
        if not out:
            self._set("error", "")
            return
        try:
            data = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            self._set("error", "")
            return
        self._set(str(data.get("state", "off")), str(data.get("detail", "") or ""))

    def _set(self, state, detail):
        if (state, detail) != (self.state, self.detail):
            self.state = state
            self.detail = detail
            self._emit()

    @property
    def is_on(self):
        return self.state in ON_STATES

    # --- writing --------------------------------------------------------
    def toggle(self):
        if not available():
            return
        if self.is_on:
            nudge("off")
            self._set("off", "")
            _spawn([DAEMON, "stop"], lambda *_: self.refresh())
        else:
            nudge("waking", "notch")
            self._set("waking", "")
            # setsid: the daemon must outlive the notch, not be its child.
            _spawn(["setsid", "-f", "env"] + _environ() + [DAEMON, "run"])

    def sending(self):
        """True while a send this widget started is still running.

        THE DAEMON DOES NOT SAY SO. `cmd_send` only publishes the `sending`
        state on its OWN path, where it has to bring the stack up itself; when
        it ATTACHes to a daemon that is already armed - which is every send in
        always-on mode - it deliberately leaves the state alone, because
        `armed` is still true and reception never stopped. So there is no state
        transition to watch, and the process itself is the only honest signal
        that the transfer is still in flight.

        /proc rather than pkill: a pattern wide enough to match the sender also
        matches the shell looking for it.
        """
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open("/proc/%s/cmdline" % entry, "rb") as handle:
                    argv = handle.read().split(b"\0")
            except OSError:
                continue
            if any(a.decode("utf-8", "replace") == SENDER for a in argv):
                return True
        return False

    def send(self, paths, receiver=None):
        """`receiver` is an id from the discovery report, not a name."""
        if not paths or not os.access(SENDER, os.X_OK):
            return False
        env = _environ()
        if receiver:
            env.append("AIRDROP_RECEIVER=%s" % receiver)
        _spawn(["setsid", "-f", "env"] + env + [SENDER] + list(paths))
        return True


# --- target discovery -----------------------------------------------------
# `airdropd send` targets `.[0].id` of the report by default, that is whichever
# peer answered mDNS first. With AirDrop set to Everyone, any Apple device in
# range is a candidate, so that default sends at random. AIRDROP_RECEIVER takes
# an id from that same report and removes the ambiguity.
REPORT = os.path.join(HOME, ".opendrop/discover.last.json")
OPENDROP = os.path.join(HOME, "owl/.venv-opendrop/bin/opendrop")

# The report ALWAYS contains our own receiver, since we advertise ourselves
# while browsing. Leaving it in would offer "send to yourself" as the first
# target.
def _own_name():
    try:
        return os.uname().nodename
    except OSError:
        return ""


def receivers():
    """[(id, name)] of the targets seen on the last browse, ourselves excluded."""
    try:
        with open(REPORT) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    mine = _own_name()
    out = []
    for entry in data if isinstance(data, list) else []:
        name = str(entry.get("name", "") or "")
        ident = str(entry.get("id", "") or "")
        if not ident or name == mine:
            continue
        out.append((ident, name or ident))
    return out


def discover(done):
    """Runs another browse, then returns with the list up to date.

    SIGINT and not SIGTERM: `opendrop find` runs indefinitely and only writes
    its report on interruption -- a SIGTERM kills it first, and the report
    stays the one from the previous browse.
    """
    if not os.access(OPENDROP, os.X_OK):
        done([])
        return
    _spawn(["timeout", "-s", "INT", "12", OPENDROP, "-i", "awdl0", "find"],
           lambda *_: done(receivers()))
