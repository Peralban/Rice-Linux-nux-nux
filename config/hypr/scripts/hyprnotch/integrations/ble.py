"""The AirDrop Continuity BLE advert, registered through bluetoothd.

WHY THE NOTCH CARRIES THIS. An iPhone only advertises itself as an AirDrop
receiver once something has woken it over Bluetooth LE. `airdropd send` does
register an advert of its own, but through `btmgmt`, and on an MT7922 that
advert does not reach the phone even on the runs where it registers without
error. Measured the same phone, same network, one minute apart:

    btmgmt advert only        phone not found, 29 s browse
    this advert running       found, sent in 8 s

So without this the Send button finds nothing, and the failure looks like the
phone's fault rather than ours.

Going through `org.bluez.LEAdvertisingManager1` asks bluetoothd to advertise
rather than working around it. Raw HCI comes back Command Disallowed because
bluetoothd owns the controller, and `btmgmt` reaches the kernel over its head.

Payload is the project's, byte for byte: manufacturer 0x004C (Apple), the
AirDrop subtype, and empty hashes, which is what "Everyone" mode needs since no
contact match is possible.
"""

import sys
import time

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib


def _log(msg):
    """Swallowing the failure here is how a dead advert looks like a phone
    problem. Anything that goes wrong has to reach the notch's stderr.

    Horodate, parce que la question n'est pas seulement « l'annonce est-elle
    partie » mais « etait-elle en vie pendant que la recherche tournait ».
    """
    print("[ble %s] %s" % (time.strftime("%H:%M:%S"), msg),
          file=sys.stderr, flush=True)

PATH = "/org/bluez/hyprnotch/adv0"
ADAPTER = "/org/bluez/hci0"
PAYLOAD = bytes.fromhex("0512000000000000000001000000000000000000")
REARM_S = 3


class _Advert(dbus.service.Object):
    def __init__(self, bus, path, on_release):
        super().__init__(bus, path)
        self.on_release = on_release

    @dbus.service.method("org.freedesktop.DBus.Properties",
                         in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != "org.bluez.LEAdvertisement1":
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs")
        return {
            "Type": dbus.String("broadcast"),
            "ManufacturerData": dbus.Dictionary(
                {dbus.UInt16(0x004C): dbus.Array(PAYLOAD, signature="y")},
                signature="qv"),
            # Left off deliberately: a legacy advert is 31 bytes and ours
            # already spends 24. TX power would risk the overflow.
            "IncludeTxPower": dbus.Boolean(False),
        }

    @dbus.service.method("org.bluez.LEAdvertisement1")
    def Release(self):
        # The only notice BlueZ gives that the advert is gone. Without
        # clearing the flag the re-arm below would believe it is still up.
        self.on_release()


class Beacon:
    """Keeps the advert up for as long as it is wanted.

    Re-arms on a timer because the MT7921/MT7922 is a combo part: bringing the
    radio up can reset the shared Bluetooth controller, and a register-once
    call is then silently dead by the time a browse runs.
    """

    def __init__(self):
        self._bus = None
        self._manager = None
        self._advert = None
        self._timer = None
        self.up = False

    def _connect(self):
        if self._manager is not None:
            return True
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._bus = dbus.SystemBus()
            # follow_name_owner_changes: a bluetoothd restart hands org.bluez
            # to a new owner, and a proxy bound to the old one throws forever.
            self._manager = dbus.Interface(
                self._bus.get_object("org.bluez", ADAPTER,
                                     follow_name_owner_changes=True),
                "org.bluez.LEAdvertisingManager1")
            self._advert = _Advert(self._bus, PATH, self._released)
        except Exception as exc:
            _log("cannot reach bluetoothd: %s" % exc)
            self._bus = self._manager = self._advert = None
            return False
        return True

    def _released(self):
        _log("released by BlueZ - re-arming")
        self.up = False

    def _arm(self):
        if not self.up and self._manager is not None:
            try:
                self._manager.RegisterAdvertisement(
                    PATH, dbus.Dictionary({}, signature="sv"),
                    reply_handler=self._ok, error_handler=self._ko)
            except Exception as exc:
                _log("register raised: %s" % exc)
        return True

    def _ok(self):
        if not self.up:
            _log("advert up")
        self.up = True

    def _ko(self, error):
        if self.up:
            _log("advert lost: %s" % error)
        else:
            _log("register failed: %s" % error)
        self.up = False

    def start(self):
        if self._timer is not None:
            return self.up
        if not self._connect():
            return False
        _log("starting")
        self._arm()
        self._timer = GLib.timeout_add_seconds(REARM_S, self._arm)
        return True

    def stop(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        if self._manager is not None and self.up:
            try:
                self._manager.UnregisterAdvertisement(PATH)
                _log("stopped")
            except Exception as exc:
                _log("unregister raised: %s" % exc)
        self.up = False
