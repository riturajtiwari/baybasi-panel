# revA vs revB — pre-order verification

Run 2026-09-21, before committing to ten boards. revA is the batch-1 design
that was fabricated, assembled and validated on the bench; everything on it
checked out except the dev-kit socket pitch. The question this answers is
whether revB differs from it in exactly two intended ways and nothing else.

Method: compare the two **board files** with KiCad's own parser, not the
generators. `git show 76fae02:hw/baybasi-ctrl.kicad_pcb` is revA.

**Result: two intended changes, no unintended ones.**

## 1. Components — SW1 added, nothing else

| | revA | revB |
|---|---|---|
| parts | 63 | 64 |
| added | | `SW1` |
| removed | | none |
| footprint substitutions | | none |

## 2. Netlist — every revA connection preserved exactly

74 nets in both.

- **Only in revB:** `COL_B0`, `COL_B1`, `COL_SP0`, `COL_SP1`
- **Only in revA:** the four `unconnected-(A1L-Pin_N-PadN)` placeholders for
  pads 9, 10, 11 and 15 — which is precisely those pads ceasing to be
  no-connects and becoming the four nets above
- **Membership change on any shared net:** exactly one, `GND` gaining `SW1`
  pads 5-8

Nothing else moved. Every other net has byte-identical pad membership.

## 3. Placement — three parts moved, all deliberately

| ref | dx | dy | rotation |
|---|---|---|---|
| A1R | +2.54 | 0 | unchanged |
| U1 | +2.50 | 0 | unchanged |
| U2 | +2.50 | 0 | unchanged |

A1R is the pitch change. U1/U2 follow it: leaving them put would have squeezed
the A1R-to-U1 channel from ~7 mm to ~4.5 mm, and the router could not keep the
B.Cu pour continuous through it. Every other part — all twelve terminals, both
W5500 headers, the whole power section, every resistor — is bit-identical.

## 4. Physical / fab

| | revA | revB |
|---|---|---|
| board outline | 4 points, 100.1 x 95.1 mm | identical |
| drill sizes | 0.8, 1.0, 1.2, 1.3, 3.2 | **identical** |
| track widths used | 0.25 mm only | 0.25 mm only |
| tracks | 444 | 495 |
| vias | 105 | 106 |

No new drill size, no new track width, same outline. Nothing that changes the
fab tier or the tooling.

## 5. The twelve output chains — zero differences

Each output was walked end to end: devkit pad -> buffer input -> buffer output
-> 330R series resistor -> terminal, with the 10k pull-down on the terminal
side.

    D1   A1L.4  -> U1.2  ... U1.18 -> R1.1  | R1.2  -> J1.1  + R16.1
    D2   A1L.5  -> U1.3  ... U1.17 -> R2.1  | R2.2  -> J2.1  + R17.1
    D3   A1L.6  -> U1.4  ... U1.16 -> R3.1  | R3.2  -> J3.1  + R18.1
    D4   A1R.4  -> U1.5  ... U1.15 -> R4.1  | R4.2  -> J4.1  + R19.1
    D5   A1R.5  -> U1.6  ... U1.14 -> R5.1  | R5.2  -> J5.1  + R20.1
    D6   A1R.18 -> U1.7  ... U1.13 -> R6.1  | R6.2  -> J6.1  + R21.1
    D7   A1R.10 -> U2.2  ... U2.18 -> R7.1  | R7.2  -> J7.1  + R22.1
    D8   A1R.9  -> U2.3  ... U2.17 -> R8.1  | R8.2  -> J8.1  + R23.1
    D9   A1R.8  -> U2.4  ... U2.16 -> R9.1  | R9.2  -> J9.1  + R24.1
    D10  A1R.7  -> U2.5  ... U2.15 -> R10.1 | R10.2 -> J10.1 + R25.1
    D11  A1R.6  -> U2.6  ... U2.14 -> R11.1 | R11.2 -> J11.1 + R26.1
    D12  A1R.17 -> U2.7  ... U2.13 -> R12.1 | R12.2 -> J12.1 + R27.1

**Chains differing from revA: 0.** Series termination and pull-downs all
present and on the same nets. This is the set that matters most: D1-D3 and D7
are the ones proven with a panel on hardware, and the rest are identical in
construction.

## 6. Where the new traces run

| net | length | layers | vias |
|---|---|---|---|
| COL_B0 | 22.6 mm | B.Cu + F.Cu | 1 |
| COL_B1 | 45.1 mm | B.Cu | 0 |
| COL_SP0 | 52.1 mm | B.Cu + F.Cu | 2 |
| COL_SP1 | 49.2 mm | B.Cu + F.Cu | 2 |

All four run SW1 (x 24) up to A1L (x 34-38), mostly on the back layer, in
y 37-77. They stay clear of the Ethernet SPI cluster (x 3-27, y 8-34) with
about 3 mm to spare, and they carry a DC level read once at boot, so length
and layer changes are irrelevant to them.

## 7. DRC

    revB: 0 violations, 0 unconnected, 7 warnings
    revA: 0 violations, 0 unconnected, 7 warnings
    all 7 in both are lib_footprint_mismatch — the same baseline

## Still needs a human before the order

1. **SW1's CPL rotation (270 deg).** Every other rotation offset in
   `make_cpl.py` was read off JLCPCB's placement overlay; this one was
   reasoned by analogy with the DIP sockets. A 180 error maps pads 1-4 onto
   5-8 and wires the column bits to GND. **Check it in their preview.**
2. **revB is a fresh autoroute.** DRC-clean is not the same as the
   field-proven routing revA carries. The net-level comparison above says the
   connectivity is identical, which is the part that matters, but the copper
   is new.
3. **`min_resolved_spokes` is back at 1**, matching what revA was fabricated
   with. At 2 the board has 5 starved-thermal errors that need layout work.
