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

## Encoding — 3 positions, GPIO 9 / 16 / 17

GPIO budget on this design: 12 outputs, SPI x4, INT, RST, /OE, sync, status =
21 pins. Free and safe (clear of USB 19/20, strapping 0/3/45/46 and the N16R8's
octal PSRAM 35/36/37): **9, 16, 17, 18**. This uses three and leaves 18 spare.

| switch | GPIO | meaning |
|---|---|---|
| SW1 | 9  | column bit 0 |
| SW2 | 16 | column bit 1 |
| SW3 | 17 | ENABLE: closed = use switches, open = use NVS |

Switch closed pulls the pin to GND; open floats to the internal pull-up.

| column | SW1 | SW2 | SW3 |
|---|---|---|---|
| 0 | off | off | **on** |
| 1 | **on** | off | **on** |
| 2 | off | **on** | **on** |
| 3 | **on** | **on** | **on** |
| use NVS | x | x | off |

**SW3 exists so that "no switches fitted" is unambiguous.** Without it, an
unpopulated board floats all pins high and reads as column 0 — so all five
batch-1 boards would claim column 0 at once. With SW3, a board with no DIP
placed reads "open" and falls through to exactly today's NVS behaviour.

Print the truth table on the silkscreen next to the switch. It costs nothing
and it is the difference between a switch block anyone can set and one that
needs this document.

## Circuit

Nothing but the switch. Three poles to three GPIOs, common side to GND,
internal pull-ups in firmware. No resistors, no caps. Read once at boot in
`identity::begin()`; do not poll (changing a column at runtime is not a thing
we want to support, and a reboot is the honest way to apply it).

## Part and JLCPCB assembly

**Yes, JLCPCB can place it, and this board is already set up for it.**
FABRICATION.md records that JLCPCB places all SMD parts *and* the through-hole
sockets, terminal blocks, inductor and electrolytics — so both SMT and THT
assembly are already in the order and neither has to be added.

Prefer an **SMD 3-position DIP switch**: SMT assembly is already happening, it
is cheaper per joint than THT, and there is no hand-soldering fee.

Expect it to be an **Extended part**, not Basic, so budget a one-time setup fee
(a few dollars) on the first order. Not per board.

I cannot verify a specific LCSC part number from here — **search the JLCPCB
parts library at order time** and pick one that is in stock, filtering for SMD,
3 position, and a footprint that matches. Record the part number in
FABRICATION.md alongside the devkit part number, for the same reason: a
reorder that quietly ships a different footprint puts you back here.

Alternative if no DIP switch is in stock at a sane price: a **1x4 pin header
with shunts** (2 shunts + 1 for enable). JLCPCB stocks headers as Basic parts
and already places THT. The tradeoff is loose shunts, which inside a sealed
enclosure is a part you will eventually drop and lose. Prefer the DIP.

## Firmware

`config.h`:

    static constexpr int PIN_COL_B0 = 9;
    static constexpr int PIN_COL_B1 = 16;
    static constexpr int PIN_COL_EN = 17;
    static constexpr uint32_t COL_IP_BASE  = 11;   // 192.168.50.(11 + column)
    static constexpr uint8_t  COL_DDP_BASE = 10;   // ddp_id = 10 + column

`identity.cpp`, in `begin()`, before the NVS read:

    pinMode(PIN_COL_B0, INPUT_PULLUP);
    pinMode(PIN_COL_B1, INPUT_PULLUP);
    pinMode(PIN_COL_EN, INPUT_PULLUP);
    delayMicroseconds(50);              // let the pull-ups settle
    if (digitalRead(PIN_COL_EN) == LOW) {
        const int8_t col = (int8_t)((!digitalRead(PIN_COL_B1) << 1)
                                  |  !digitalRead(PIN_COL_B0));
        // Everything else follows from the column - see the table above.
        // Nothing is written to NVS: the switches ARE the configuration, and
        // persisting them would create a second source of truth that can
        // disagree with the hardware.
        ...
    }

Rules that matter:

- **Switches win over NVS when SW3 is closed.** Two sources of truth is the
  failure this is meant to remove, so there is a strict precedence, not a merge.
- **Do not write the switch-derived column to NVS.** A board moved to another
  slot must follow its switches, not a stale memory of where it used to be.
- **An `assign` command aimed at a switch-configured board should be refused,
  with an ack that says why.** Silently accepting it and then ignoring it on the
  next boot is worse than refusing.
- Announce the source in the heartbeat (`"col_src":"dip"` / `"nvs"`), so
  `baybasi discover` shows at a glance which boards are self-configured.

## gen_pcb.py

- One 3-position DIP footprint, near the devkit socket and reachable with the
  board mounted - it will be set with the board in hand, but read with it in
  place.
- Three traces to devkit pads for GPIO 9, 16, 17, plus GND.
- Silkscreen: the truth table, and a mark for the ON direction.
- Re-run the DRC/route pass; this is the first new footprint since revA.

## Honest cost

The batch-2 change list was one line (`A1L/A1R` 22.86 -> 25.4 mm). This adds a
footprint, three traces, silkscreen and a routing pass, plus firmware and a new
part in the BOM. It is a real increase in respin scope and wants a careful DRC.

Worth it on the grounds that the respin is happening anyway, the marginal
layout work is small, and it removes an entire class of install-day error -
including the one that silently duplicates a quarter of the wall.
