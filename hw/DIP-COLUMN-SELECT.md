# Column select by DIP switch — spec for batch 2

Status: **proposed 2026-09-20**, not built. Decide before the batch-2 layout.

## The problem it solves

A board's column currently lives in NVS and is set over the network by
`baybasi assign <mac> <column>`. That works, and `identify` (added 2026-09-20)
makes it usable on a wall. But it rests on a binding no machine can check:
**which MAC is in which physical column.** The MAC is the ESP32's factory eFuse
value, not printed on the jack, the module or the board, so today the answer is
"read it on the bench and put a sticker on". A workflow that needs a sticker to
function has a gap in it.

DIP switches close it by kind, not by degree. `identify`, DHCP reservations and
power-on ordering are all ways of *discovering* a binding a human established
and must not forget. **Switches make the hardware state its own position.**
Replace a board: set the switches to match the slot, done — no laptop, no
discovery, no MAC lookup, no Pi.

## What it retires

The production addressing is a pure function of the column:

| column | IP | ddp_id |
|---|---|---|
| 0 | 192.168.50.11 | 10 |
| 1 | 192.168.50.12 | 11 |
| 2 | 192.168.50.13 | 12 |
| 3 | 192.168.50.14 | 13 |

`ip = 192.168.50.(11 + column)`, `ddp_id = 10 + column`. So a board that knows
its column derives its whole network identity. **Commissioning disappears
entirely** for boards with switches fitted: power up, read switches, take the
static address, start receiving. No discover, no assign, no reboot-on-assign,
no NVS write, nothing for the operator to type or get wrong.

`assign` and `identify` stay, for batch-1 boards and as a fallback.

## Encoding — 2 positions, GPIO 9 / 16

**Revised 2026-09-20.** The first draft used three positions, the third an
ENABLE, so that "no switches set" was distinguishable from "column 0". Two
bits gives four codes and that wanted five states, hence the extra pin.

Dropped, because the fifth state was not worth it:

- The only boards with no DIP are batch 1, which are bench-only - wrong socket
  pitch, never going in the wall. A build flag covers them if one ever needs a
  column.
- "Someone forgot to set the switches" is real - all four boards read 00, all
  claim column 0, all take .11, and four hosts on one IP is an ugly failure.
  But it is trivially visible in software: four boards announcing col:0. That
  belongs in a `baybasi verify` check, not in a GPIO.

What the two-bit version buys back is worth more than the state it gives up:
**00 / 01 / 10 / 11 needs no explanation.** The silkscreen is two labels, not a
truth table, and nobody setting a board on a ladder needs this document open.

## Pin assignment

GPIO budget on this design: 12 outputs, SPI x4, INT, RST, /OE, sync, status =
21 pins. Free and safe (clear of USB 19/20, strapping 0/3/45/46 and the N16R8's
octal PSRAM 35/36/37): **9, 16, 17, 18**. This uses three and leaves 18 spare.

| switch | GPIO | meaning |
|---|---|---|
| SW1 | 9  | column bit 0 |
| SW2 | 16 | column bit 1 |

Switch closed pulls the pin to GND; open floats to the internal pull-up. The
firmware inverts, so **closed = 1**.

| column | SW2 | SW1 |
|---|---|---|
| 0 | off | off |
| 1 | off | **on** |
| 2 | **on** | off |
| 3 | **on** | **on** |

GPIO 17 and 18 stay free.

Silkscreen: label the poles `2` and `1` by binary weight and print
`COLUMN = 2+1`. Two labels, no table, nothing to look up.

**Switches are authoritative on any board that has them.** There is no merge
with NVS and no enable bit - one source of truth was the whole point. An
`assign` command aimed at such a board is refused with an ack saying why.

**Consequence, accepted:** a board with no DIP fitted reads 00 and becomes
column 0, so batch-1 boards cannot be commissioned over the network under this
firmware. They are bench-only and one at a time, where column 0 is what you
want anyway. If that ever changes, a `-DNO_COLUMN_DIP` build restores the NVS
path.

## Circuit

Nothing but the switch. Three poles to three GPIOs, common side to GND,
internal pull-ups in firmware. No resistors, no caps. Read once at boot in
`identity::begin()`; do not poll (changing a column at runtime is not a thing
we want to support, and a reboot is the honest way to apply it).

## Part and JLCPCB assembly

**Checked against the JLCPCB assembly parts library, 2026-09-20.** The earlier
advice in this doc - "prefer an SMD 2-position DIP switch" - does not survive
contact with what they actually stock.

Searching "DIP Switch" returns 12 parts. **Exactly one has stock:**

| | |
|---|---|
| Part | **C99987**, Diptronics **EI-04** |
| Type | 4 position, **through-hole**, 2.54 mm pitch, SPST slide |
| Rating | 24 V / 25 mA - fine for logic-level GPIO |
| Stock | 103 |
| Price | $0.52 at qty 1, $0.36 at 47+ |
| Class | Extended, so a one-time setup fee |

Everything else in that search is stock 0 and marked **Consign Part**, meaning
you buy and ship the parts yourself. That includes `CSWDIP-2P` (C9900014698),
the 2-bit SMD part that would otherwise have been the obvious choice.

### Use the 4-position part, and wire all four poles

The EI-04 being 4-position is not a compromise - it is better than the
2-position this doc specced. Use poles 1-2 for the column and **wire poles 3
and 4 to the free GPIOs 17 and 18**. Two spare configuration bits, already
placed, already routed, costing nothing. Leave them unread in firmware until
there is something to read.

That also empties the GPIO budget, which is the tradeoff: after this there are
no free pins on this design. Worth it for switches that are placed anyway.

Through-hole is not a problem - JLCPCB already places the sockets, terminal
blocks, inductor and electrolytics on this board, so THT assembly is in the
order regardless.

**Stock of 103 is thin.** It covers ten boards comfortably but could be gone
by order day. Check before finalising, and record the part number in
FABRICATION.md next to the devkit's.

### If EI-04 is out of stock

**Pin header plus shunts.** Headers are stocked in enormous depth (C2333,
2.54 mm 2x40P, 25,000+ in stock, $0.32) and snap to whatever length is needed.
A 1x3 with the centre pin to GND takes two shunts. Cheaper and never
unavailable; the cost is loose shunts, which inside a sealed enclosure is a
part you will eventually drop and lose.

**Or consign.** Buy 2-position SMD DIP switches from LCSC and ship them to
JLCPCB. Most control, most hassle, and it puts a manual step in every reorder.

## Firmware

`config.h`:

    static constexpr int PIN_COL_B0 = 9;
    static constexpr int PIN_COL_B1 = 16;
    static constexpr uint32_t COL_IP_BASE  = 11;   // 192.168.50.(11 + column)
    static constexpr uint8_t  COL_DDP_BASE = 10;   // ddp_id = 10 + column

`identity.cpp`, in `begin()`, before the NVS read:

    pinMode(PIN_COL_B0, INPUT_PULLUP);
    pinMode(PIN_COL_B1, INPUT_PULLUP);
    delayMicroseconds(50);              // let the pull-ups settle
    {
        const int8_t col = (int8_t)((!digitalRead(PIN_COL_B1) << 1)
                                  |  !digitalRead(PIN_COL_B0));
        // Everything else follows from the column - see the table above.
        // Nothing is written to NVS: the switches ARE the configuration, and
        // persisting them would create a second source of truth that can
        // disagree with the hardware.
        ...
    }

Rules that matter:

- **Switches win over NVS, always.** Two sources of truth is the failure this
  is meant to remove, so there is a precedence, not a merge.
- **Do not write the switch-derived column to NVS.** A board moved to another
  slot must follow its switches, not a stale memory of where it used to be.
- **An `assign` command aimed at a switch-configured board should be refused,
  with an ack that says why.** Silently accepting it and then ignoring it on the
  next boot is worse than refusing.
- Announce the source in the heartbeat (`"col_src":"dip"` / `"nvs"`), so
  `baybasi discover` shows at a glance which boards are self-configured.

## gen_pcb.py

- One **4-position** DIP footprint (Diptronics EI-04, THT 2.54 mm), near the
  devkit socket and reachable with the board mounted - it will be set with the board in hand, but read with it in
  place.
- Four traces to devkit pads for GPIO 9, 16, 17, 18, plus a common GND.
  Poles 3 and 4 are spares - placed and routed now, unread until needed.
- Silkscreen: poles 1 and 2 marked `1` and `2` by binary weight with
  `COLUMN = 2+1`; poles 3 and 4 marked `SPARE`. Mark the ON direction.
- Re-run the DRC/route pass; this is the first new footprint since revA.

## Honest cost

The batch-2 change list was one line (`A1L/A1R` 22.86 -> 25.4 mm). This adds a
footprint, four traces, silkscreen and a routing pass, plus firmware and a new
part in the BOM. It is a real increase in respin scope and wants a careful DRC.

Worth it on the grounds that the respin is happening anyway, the marginal
layout work is small, and it removes an entire class of install-day error -
including the one that silently duplicates a quarter of the wall.


## Follow-on: `baybasi verify`

Two bits means "switches never set" reads as column 0, so four unset boards
all claim column 0 and all take 192.168.50.11. Four hosts on one address is an
ugly, confusing failure - and a cheap one to catch. Before any media:

- listen for announcements
- assert four boards, columns 0-3 exactly once each, on the IPs wall.yaml
  expects
- report anything missing, duplicated or unexpected

It cannot confirm physical position - `baybasi pattern id` is still the check
that closes that loop - but it catches every wiring-independent mistake,
including the one this encoding trades away.
