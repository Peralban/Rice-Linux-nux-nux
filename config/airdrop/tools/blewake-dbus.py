#!/usr/bin/env python3
"""AirDrop Continuity BLE advert, via bluetoothd's D-Bus API.

Why this exists alongside tools/blewake.sh: on this machine `btmgmt add-adv`
(what blewake.sh and airdrop-helper both use) FAILS outright once airdrop.sh's
layer 1 has swept the radio - "failed to register the advertising instance" -
and where it does succeed, the phone never reacts to it. bluetoothd owns
advertising on a system where it runs; going through LEAdvertisingManager1
lets it enable the advertising itself, which is the path BlueZ expects.

Payload is byte-identical to the project's:
    17 FF 4C00 05 12 00*8 01 00*8
i.e. manufacturer 0x004C (Apple) with the AirDrop subtype and empty hashes,
which is what "Everyone" mode needs - no contact match is possible.

Run it in its own terminal and leave it there:
    tools/blewake-dbus.py
    ./airdrop.sh send <file>
"""
import signal
import sys

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

PATH = "/org/bluez/airdrop/adv0"
ADAPTER = "/org/bluez/hci0"
PAYLOAD = bytes.fromhex("0512000000000000000001000000000000000000")


class Advertisement(dbus.service.Object):
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
            # Left off deliberately: the legacy advert is 31 bytes total and
            # ours already spends 24. TX power would risk the overflow.
            "IncludeTxPower": dbus.Boolean(False),
        }

    @dbus.service.method("org.bluez.LEAdvertisement1")
    def Release(self):
        pass


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    # THE REFERENCE IS LOAD-BEARING: without it Python collects the object,
    # its D-Bus path disappears, and BlueZ drops the advert without a word.
    adv = Advertisement(bus, PATH)
    manager = dbus.Interface(bus.get_object("org.bluez", ADAPTER),
                             "org.bluez.LEAdvertisingManager1")
    loop = GLib.MainLoop()
    state = {"up": False}

    def ok():
        if not state["up"]:
            print("advert up", flush=True)
        state["up"] = True

    def ko(error):
        if state["up"]:
            print("advert lost (%s) - re-arming" % error, flush=True)
        state["up"] = False

    # The MT7921/MT7922 is a combo Wi-Fi/BT part, so reconfiguring the radio
    # RESETS the shared Bluetooth controller and takes the advert down with
    # it - which is exactly what airdrop.sh's layer 1 does, and why a
    # register-once script is silently dead by the time the browse runs.
    # Re-arming on a timer makes the launch order irrelevant.
    def arm():
        if not state["up"]:
            try:
                manager.RegisterAdvertisement(
                    PATH, dbus.Dictionary({}, signature="sv"),
                    reply_handler=ok, error_handler=ko)
            except Exception as exc:
                print("register: %s" % exc, file=sys.stderr, flush=True)
        return True

    arm()
    GLib.timeout_add_seconds(3, arm)

    def stop(*_):
        try:
            manager.UnregisterAdvertisement(PATH)
        except Exception:
            pass
        loop.quit()
        return False

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, stop)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, stop)
    loop.run()


if __name__ == "__main__":
    main()
