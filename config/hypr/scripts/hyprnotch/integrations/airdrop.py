"""Pont vers `airdropd`, le démon AirDrop du projet airdrop-mt7921.

Tout passe par le binaire du démon : lui seul sait parler au wrapper
privilégié, et lui seul tient le verrou qui empêche deux bascules
simultanées pendant les ~20 s de montée de la radio.

Rien n'est interrogé tant que la page n'est pas visible : `set_live()`
suit la même discipline que le widget système.
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

# Ce que la barre du projet amont exporte aussi : l'interrupteur doit
# vouloir dire « on peut te droper dessus maintenant », sans étape BLE et
# sans lâcher l'association Wi-Fi — soit always-on + P2P-GO.
ENV = {"AIRDROP_ALWAYS": "1", "AIRDROP_DUALCHAN": "1"}

STATE_FILE = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "airdropd", "state.json")

# Les états que le démon publie, et ce qu'ils veulent dire pour l'utilisateur.
# « on » ne recouvre pas que `armed` : pendant la montée et pendant un envoi
# la radio EST allumée, et afficher « off » là donne l'impression que la
# bascule a échoué.
ON_STATES = ("idle", "waking", "armed", "switching", "unreachable", "sending")


def _environ():
    env = dict(os.environ)
    env.update(ENV)
    return ["%s=%s" % kv for kv in env.items()]


def _spawn(argv, done=None):
    """Lance une commande sans bloquer la boucle GTK."""
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
    """État optimiste, écrit par le clic et non par le démon.

    Allumer la radio prend une vingtaine de secondes. Sans ça, l'interrupteur
    garde son ancien libellé pendant plusieurs sondages après le clic, ce qui
    le fait passer pour cassé — et donc recliquer, ce qui est exactement la
    course que le verrou du démon existe pour empêcher.
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

    # --- lecture --------------------------------------------------------
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

    # --- écriture -------------------------------------------------------
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
            # setsid : le démon doit survivre au notch, pas en être l'enfant.
            _spawn(["setsid", "-f", "env"] + _environ() + [DAEMON, "run"])

    def send(self, paths, receiver=None):
        """`receiver` est un id du rapport de decouverte, pas un nom."""
        if not paths or not os.access(SENDER, os.X_OK):
            return False
        env = _environ()
        if receiver:
            env.append("AIRDROP_RECEIVER=%s" % receiver)
        _spawn(["setsid", "-f", "env"] + env + [SENDER] + list(paths))
        return True


# --- decouverte des cibles ------------------------------------------------
# `airdropd send` cible par defaut `.[0].id` du rapport, c'est-a-dire le
# premier qui a repondu au mDNS. Avec AirDrop en « Tout le monde », tout
# appareil Apple a portee est candidat, donc ce defaut envoie au hasard.
# AIRDROP_RECEIVER prend un id de ce meme rapport et leve l'ambiguite.
REPORT = os.path.join(HOME, ".opendrop/discover.last.json")
OPENDROP = os.path.join(HOME, "owl/.venv-opendrop/bin/opendrop")

# Le rapport contient TOUJOURS notre propre receveur, puisqu'on s'annonce
# nous-memes pendant qu'on browse. L'y laisser proposerait « s'envoyer a
# soi-meme » comme premiere cible.
def _own_name():
    try:
        return os.uname().nodename
    except OSError:
        return ""


def receivers():
    """[(id, nom)] des cibles vues au dernier browse, nous exclus."""
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
    """Relance un browse, puis rend la main avec la liste a jour.

    SIGINT et pas SIGTERM : `opendrop find` tourne indefiniment et n'ecrit son
    rapport que sur interruption - un SIGTERM le tue avant, et le rapport
    reste celui du browse precedent.
    """
    if not os.access(OPENDROP, os.X_OK):
        done([])
        return
    _spawn(["timeout", "-s", "INT", "12", OPENDROP, "-i", "awdl0", "find"],
           lambda *_: done(receivers()))
