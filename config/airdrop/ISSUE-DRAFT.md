# MT7922 on Arch: `-S widen` gets the transfer tail through sometimes, plus 6 portability fixes

Thanks for publishing this — the write-ups in `docs/FINDINGS.md` are what made
the rest of this possible to debug rather than guess at.

Reporting from hardware you have not tested: **MT7922** (not MT7921), same
`mt7921e` driver.

| | |
|---|---|
| Chipset | MEDIATEK MT7922 `[14c3:0616]`, driver `mt7921e` |
| Distro / kernel | Arch Linux, `7.2.4-arch1-2` (not the pinned 6.12.97) |
| Python / zeroconf / opendrop | 3.14.7 / 0.151.3 / 0.13.0 |
| Phone | iPhone 17, iOS 27.0 |

**Receiving completed for the first time** on this setup — a 1,801,207-byte
JPEG arrived whole (`ffd8`…`ffd9`, EXIF intact) — though only on 1 of 6
attempts. Details in §1.

---

## 1. Limitation #1 ("the tail of a transfer is lost") — `-S widen` sometimes gets past it

`daemon/README.md` lists the lost tail as **cause unknown**, with an untested
hypothesis:

> INTERSECT mirrors the peer downward, so a brief dip narrows our
> advertisement, which may make it dip further — a feedback collapse.

Switching the helper default from `intersect` to `widen` produced **the first
completed transfer I have seen on the daemon path** — but it is not a fix, and
I want to be careful not to overstate it.

Measured, same phone, same file, same channel:

| strategy | slot overlap | outcome |
|---|---|---|
| `intersect` | 1/16 | stalled at 1,699,103 / 1,801,207 (94%), never completed |
| `widen` | 3/16 – 8/16 | 6 uploads started, **2** reached `POST /Upload 200`, **1** verified byte-exact and usable |

So `widen` moves it from "never completes" to "completes maybe a third of the
time", and raises overlap severalfold. The one confirmed success was a
1,801,207-byte JPEG, whole (`ffd8`…`ffd9`, EXIF intact, matching `TotalBytes`).
The other five attempts left partial `.dvzip` files, one as close as
1,798,990 / 1,801,207 — so the tail is still lost most of the time, just less
often.

I cannot claim this confirms the feedback-collapse hypothesis. What it shows is
that the advertised sequence measurably affects whether the tail survives,
which at least makes the hypothesis testable rather than speculative. Anyone
reproducing this should note both strategies were run against iOS 27, and that
`intersect` is currently the hardcoded default in `airdrop-helper`:

```sh
strategy="${AIRDROP_OWL_STRATEGY:-intersect}"
```

Given `intersect` never completed here and `widen` sometimes does, the default
may be worth revisiting — though on hardware where the radio genuinely follows
the sequence, the tradeoff could differ.

## 2. `PHY` is hardcoded to `phy0` in `airdrop-helper`

```sh
PHY="${PHY:-phy0}"
```

`airdrop.sh` derives it correctly from the interface, and the helper's own
comments acknowledge the phy "is not always phy0" — but the helper never does.
After any driver reload the card can come back as `phy1`, and then:

```
iw phy phy0 interface add go0 type __p2pgo
  -> command failed: No such file or directory (-2)
```

which `airdropd` surfaces as the very misleading
`no privilege or go0 setup failed - see README (sudoers)`. I spent a while on
sudoers before finding it was ENOENT on the phy.

Fix — same approach `airdrop.sh` already uses:

```sh
PHY="${PHY:-}"
# ... after IFACE is resolved ...
if [ -z "$PHY" ] && [ -n "$IFACE" ]; then
  PHY=$(basename "$(readlink -f "/sys/class/net/$IFACE/phy80211")" 2>/dev/null)
fi
PHY="${PHY:-phy0}"
```

## 3. `MT76` is computed before `$PHY` is known — the runtime-pm workaround silently no-ops

Line 27 of `airdrop-helper`:

```sh
MT76=/sys/kernel/debug/ieee80211/$PHY/mt76
```

With the fix above (or any case where `PHY` is resolved later) this expands
with an empty `PHY`, giving `/sys/kernel/debug/ieee80211//mt76`, and both
writes fail:

```
airdrop-helper: line 250: /sys/kernel/debug/ieee80211//mt76/runtime-pm: No such file or directory
airdrop-helper: line 251: /sys/kernel/debug/ieee80211//mt76/deep-sleep: No such file or directory
```

This is the nastier of the two, because it is exactly the failure your README
warns about: runtime PM stays on, monitor RX goes silent, **and nothing reports
an error**. Moving the assignment after `PHY` is finalised fixes it.

## 4. `AirDropBrowser` has no `update_service` — kills the mDNS browse thread

With `zeroconf` 0.151.3, `update_service` is mandatory. The long-standing
`FutureWarning` is now fatal:

```
Exception in thread zeroconf-ServiceBrowser-_airdrop._tcp-26377:
AttributeError: 'AirDropBrowser' object has no attribute 'update_service'
```

It is raised **inside the browser thread**, so the thread dies and no discovery
arrives afterwards. This is not a rare path: a receiver that re-announces —
which is what an iPhone does when its AirDrop state changes, and what
`opendrop-mdns-reannounce.patch` makes this side do too — fires an `update`
rather than an `add`. The peer you are looking for is precisely the one that
takes the browse down.

Patch attached below as `opendrop-zeroconf-update-service.patch`; it reports an
update the same way as an add.

## 5. `REG` defaults to `NZ`, and never reaches the helper anyway

Two separate problems:

**a.** `country_code=${REG:-NZ}` bakes in your regulatory domain. In France,
ch149 (5745 MHz) is not allocated, so `go_target`'s last-resort ch149 arm
produces:

```
Frequency 5745 (primary) not allowed for AP mode, flags: 0x853 NO-IR
go0: AP-DISABLED
```

Worse, because the station was associated to an AP advertising `Country: FR`,
the kernel intersects that with hostapd's `NZ` hint, so ch149 stays NO-IR no
matter what `REG` says. Every bring-up failed until the GO was moved to ch36.

**b.** `airdropd` invokes the helper as `sudo -n "$HELPER"` with no `-E`, so
`REG` (and `AIRDROP_OWL_STRATEGY`) from `~/.config/airdrop/config` never cross
into it. The documented "set REG to your country" has no effect on the daemon
path — the helper's compiled-in default always wins.

Worth either passing these through explicitly, or documenting that the daemon
path ignores them.

## 6. `ping6` no longer exists on modern iputils

Layer 2.5 in `airdrop.sh`:

```
timeout: failed to run command 'ping6': No such file or directory
```

iputils merged it into `ping -6` years ago; Arch ships no `ping6`. The failure
is silent-ish and **actively misleading**, because with no packets sent the
counters read `to_peer=0`, and the script concludes:

```
==> NO PING REPLIES - treat this as a real failure of the TX path.
```

I chased a nonexistent TX fault on the strength of that. `ping -6` is portable
and gives a real answer (on the run where it worked: `to_peer=9`, 0 replies —
genuinely useful).

## 7. Build and setup papercuts on a current distro

- **cmake 4.x refuses the `radiotap` submodule** (`compatibility with CMake <
  3.5 removed`). `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` gets past it. The
  vendored googletest also fails to compile with modern GCC (`uintptr_t` not
  declared), but the `owl` binary links fine before that, so it is harmless.
- **Patch order in the README breaks the daemon path.** `opendrop-url-items`
  anchors on the `detail = ", ".join(names[:3])` block that
  `opendrop-ask-confirm` introduces. Applied in the README's order,
  `ask-confirm` comes last and the `url-items` hunk lands **inside
  `handle_ask`** instead, producing an `IndentationError` at import. Applying
  `ask-confirm` before `url-items` fixes it. (Also: `git apply` rejects several
  patches on whitespace; `patch -F2` takes them, but fuzz is how the above
  mislands — worth pinning the order in the README.)
- **`airdrop-confirm` is swaynag-only**, so on any non-sway compositor it fails
  closed and every transfer is declined:
  `swaynag not found - DECLINING (cannot ask, so cannot consent)`.
  `hyprland-dialog` covers Hyprland and is *simpler* — it writes the chosen
  button to stdout, which removes the marker-file dance and the 2 ms race it
  exists to work around. Happy to send that as a PR if useful.
- **NetworkManager manages `go0`** unless told otherwise: it runs DHCP on it and
  the lease **takes over the default route**, which drops the station. Worth a
  line in the README:
  ```
  /etc/NetworkManager/conf.d/99-airdrop-unmanaged.conf
  [keyfile]
  unmanaged-devices=interface-name:go0;interface-name:mon0;interface-name:mon1;interface-name:awdl0
  ```

---

## Still broken here: sending — the BLE wake never wakes the phone

Not asking you to fix this, just recording it in case it is a data point.

AWDL itself is fine in both directions: `airdrop.sh` finds the peer every time,
reads its sequence (`36,0,149,0,0,0,0,0,6,0,44,0,0,0,0,0`), establishes the
IPv6 neighbour, and mDNS flows (`from_peer=49`). But the phone never advertises
`_airdrop._tcp`, so discovery only ever returns this machine.

`tools/blewake.sh` **fails outright** here once layer 1 has swept the radio:

```
failed to register the advertising instance
```

`btmgmt add-adv` succeeds when the P2P-GO stack is up but fails after
`airdrop.sh`'s channel sweep — consistent with §36's combo-chip controller
reset, just more aggressively. I also wrote a `bluetoothd`/D-Bus
`LEAdvertisingManager1` equivalent that registers cleanly and re-arms every 3s
across controller resets; the phone still does not react to it. Without a
second BLE-capable device I cannot tell whether the frame is on air at all, so
I have not concluded anything about the cause.
