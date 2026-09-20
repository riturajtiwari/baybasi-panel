# Board bring-up — BAYBASI COLUMN CTRL revA, batch 1

Validation procedure for the five assembled boards, 2026-09-15.

**Constraint this is written around:** the ESP32-S3 devkits in hand have their
header rows at **25.4 mm**; A1L/A1R are at **22.86 mm**. The **left row seats,
the right row does not.** Everything below works with the devkit half-seated.
Batch 2 will move A1L/A1R to 25.4 mm — see FABRICATION.md.

Every pin number below is extracted from `net.net`, not counted by hand.

Work top to bottom. Each step gates the next, so a failure is isolated to the
step that found it. **Do not skip step 0** — it is the one that catches an
assembly fault before you put energy into it.

---

## Step 0 — Meter only. No power, no ICs, no devkit, no W5500

### 0.1 Visual

- Solder bridges, especially across U1/U2 socket pins and the 0805 rows.
- All twelve terminal blocks: wire entry faces the board edge, matching the
  silkscreen arrow.
- Electrolytics C1–C4: stripe matches the silkscreen.

### 0.2 The supply input must not be a short

**J13 pin 1 (`+`, square pad) to J13 pin 2 (GND).**

Expect a **brief** beep as C1–C4 charge from the meter's own ~1 mA, then a
reading climbing into the kΩ. **A beep that never stops is a short — stop here.**
Short the terminals before repeating, or the caps are still charged and you will
see nothing the second time.

### 0.3 Output chain sweep — the big one

ICs **out** of their sockets. Probe socket pin to terminal block. This proves all
twelve series resistors, both buffers' output traces and every connector, with no
power anywhere.

| Out | Socket pin | Terminal | Expect |
|---|---|---|---|
| D1 | U1 pin 18 | J1 pin 1 | **330 Ω** |
| D2 | U1 pin 17 | J2 pin 1 | 330 Ω |
| D3 | U1 pin 16 | J3 pin 1 | 330 Ω |
| D4 | U1 pin 15 | J4 pin 1 | 330 Ω |
| D5 | U1 pin 14 | J5 pin 1 | 330 Ω |
| D6 | U1 pin 13 | J6 pin 1 | 330 Ω |
| D7 | U2 pin 18 | J7 pin 1 | 330 Ω |
| D8 | U2 pin 17 | J8 pin 1 | 330 Ω |
| D9 | U2 pin 16 | J9 pin 1 | 330 Ω |
| D10 | U2 pin 15 | J10 pin 1 | 330 Ω |
| D11 | U2 pin 14 | J11 pin 1 | 330 Ω |
| D12 | U2 pin 13 | J12 pin 1 | 330 Ω |

Then, every `J`n **pin 1 to GND: 10 kΩ** (R16–R27, the output pull-downs), and
every `J`n **pin 2 to GND: 0 Ω**.

`J`n pin 1 is the **square** pad — the silkscreen says `J1-J12: SQ PAD = DATA`.

### 0.4 Enable and power nets

| Check | Expect |
|---|---|
| U1 pin 19 ↔ U2 pin 19 ↔ A1L pin 12 | 0 Ω — one net, `OE_N` |
| U1 pin 19 to +3V3E (M2 pin 2) | 10 kΩ — R15 pull-up |
| A1L pin 21 ↔ U1 pin 20 ↔ U2 pin 20 | 0 Ω — the 5 V rail |
| J13 pin 1 to A1L pin 21 | a **diode drop**, not 0 Ω — through Q1 |
| A1L pin 22, A1R pins 1/21/22, U1 pins 8/10 to J13 pin 2 | 0 Ω — GND |
| A1L pin 8 to M2 pin 5 | 0 Ω — `ETH_RST` |

---

## Step 1 — Power, nothing fitted

Bench supply to **5.00 V** with the **current limit at 100 mA**. The limit is the
safety net: a fault trips it instead of burning a trace.

Apply to J13, square pad positive.

| Measure | Expect |
|---|---|
| Supply current | a few mA. **If it sits at the 100 mA limit, stop** |
| U1 pin 20 | ~4.7 V (5 V less Q1's drop) |
| M2 pin 2 (+3V3E) | 3.3 V — U3 is alive |
| U1 pin 19 (/OE) | ~3.3 V — outputs **disabled**, which is correct with no devkit |

### 1.1 Reverse polarity, once (optional)

Still limited to 100 mA, reverse the supply leads. Expect **~0 mA** — Q1 blocking.
This validates the QA fix from 2026-09-07, where S and D were transposed and the
body diode would have passed a reversed supply. Restore correct polarity after.

---

## Step 2 — Devkit, left row only

Power off. Seat the devkit's **left** row in A1L, USB ports toward the bottom edge.

- **Insulate the unseated right row.** Those pins sit over U2's socket and the
  output resistors. Card or Kapton underneath.
- Support the raised side so the seated pins do not carry a bending moment.

Raise the current limit to 500 mA. Power from **J13 only, no USB**.

**The devkit should come up.** That proves A1L pins 21 and 22 are making real
contact — the two that matter most, tested in one second.

---

## Step 3 — Flash, and prove the /OE path

USB to the devkit's **COM** port (the UART bridge).

```bash
cd fw-bench
pio run -e ctrl-all12 -t upload
```

**Flash `ctrl-all12`, not `ctrl-board`.** It drives all twelve outputs from one
binary, each in its own colour, with **N white pixels at the head of the chain
where N is the output number**. So you flash once and then just move a panel
around: no rebuild between outputs, and if you plug into J7 and count six white
pixels you have found a wiring error rather than a dead output.

With the devkit half-seated it still works for D1-D3; D4-D12 simply have nothing
on the other end yet.

Monitor on the **USB** port — the env sets `ARDUINO_USB_CDC_ON_BOOT=1`.

The banner prints, including `/OE on GPIO 8 driven LOW: 245 outputs enabled`.

**Now measure U1 pin 19: it must be LOW (< 0.4 V).** It was 3.3 V in step 1. That
transition proves the whole /OE path — devkit GPIO 8, A1L pin 12, the trace, both
buffers — through a socket contact you cannot see.

---

## Step 4 — U1 and the first panel

**Power everything down first.**

### 4.1 Form the DIP legs

New DIP ICs ship with their leads splayed to ~8.5 mm for auto-insertion. The
socket is **7.62 mm**. Press an unformed DIP onto a socket and it perches on top
making no contact.

Lay the IC on its side on a flat hard surface, legs against the surface, and roll
the body toward the legs until that row is parallel and vertical. Flip, repeat.

**Check pin 1 against the socket notch and the silkscreen.** A '245 in backwards
puts 5 V on the outputs and ground on VCC. Insert until the body is flush, then
pull it back out once — a seated DIP resists. If it lifts away freely it was never in.

### 4.2 Wire the panel

- Panel 5 V and GND **from the bench supply on its own thick leads**. Never from
  this board. J1–J12 carry DATA + GND only, which is exactly why this board
  cannot repeat the dev-kit failure of 2026-09-13.
- Panel **DIN → J1 pin 1** (square pad).
- Panel **GND → J1 pin 2**. Keep the panel's power leads short and thick so this
  signal ground carries negligible current.

### 4.3 Light it

Start with a small budget. 256 LEDs at white is 15.4 A; FastLED scales the frame
to fit whatever you declare.

```bash
PLATFORMIO_BUILD_FLAGS="-DSUPPLY_MA=1000" pio run -e ctrl-board -t upload
```

**Panel supply on first, board second.** Every time.

Expect the four bench patterns, dim. Raise `SUPPLY_MA` toward what the supply can
actually deliver once it works.

---

## Step 5 — D2 and D3

Move the panel to J2, rebuild with `-DLED_PIN=5`. Then J3 with `-DLED_PIN=6`.

Three of U1's six outputs proven. D4–D12 need the right row.

---

## Step 6 — U2, one jumper at a time

Fit U2 (form the legs, check pin 1). Its inputs come from the right row.

**Best method: put the devkit in a breadboard** and run **male-to-male** jumpers
from the breadboard rows into the socket holes. The breadboard gives strain
relief and a stable platform, which flying leads onto bare header pins do not.
Devkit from USB, board from J13, and the GND jumper is what ties them.

Fourteen jumpers reach everything. **Count holes from the TOP of the board.**

| Signal | Devkit pin | Hole |
|---|---|---|
| GND | GND | A1L 22 |
| /OE | 8 | A1L 12 |
| D1 | 4 | A1L 4 |
| D2 | 5 | A1L 5 |
| D3 | 6 | A1L 6 |
| D4 | 1 | A1R 4 |
| D5 | 2 | A1R 5 |
| D6 | 21 | A1R 18 |
| D7 | 38 | A1R 10 |
| D8 | 39 | A1R 9 |
| D9 | 40 | A1R 8 |
| D10 | 41 | A1R 7 |
| D11 | 42 | A1R 6 |
| D12 | 47 | A1R 17 |

A second GND jumper (A1R 1, 21 or 22) costs nothing and helps if you see flicker.

Do **not** jumper 5 V: the devkit's 5 V pin back-feeds this board through Q1.

**Count check before trusting it:** A1R holes 1, 21 and 22 are all GND, so all
three are dead shorts to J13 pin 2. If they are not, you are counting from the
wrong end.

Which buffer each output goes through, for fault isolation:

| Out | Devkit pin | A1R hole | Terminal | Buffer |
|---|---|---|---|---|
| D4 | 1 | 4 | J4 | U1 |
| D5 | 2 | 5 | J5 | U1 |
| D6 | 21 | 18 | J6 | U1 |
| D7 | 38 | 10 | J7 | **U2** |
| D8 | 39 | 9 | J8 | U2 |
| D9 | 40 | 8 | J9 | U2 |
| D10 | 41 | 7 | J10 | U2 |
| D11 | 42 | 6 | J11 | U2 |
| D12 | 47 | 17 | J12 | U2 |

**D7 is the one that matters** — it is the first output through U2, so it proves
the second buffer, its supply and its enable. With `ctrl-all12` there is nothing
to rebuild; just move the panel to J7 and count seven white pixels.

Verify the hole count before trusting it: A1R pin 1, 21 and 22 are all GND, so
holes 1, 21 and 22 are dead shorts to J13 pin 2. If they are not, you are counting
from the wrong end.

---

## Step 7 — Ethernet

Every W5500 signal is on the seated left row, so this needs no jumpers.

Fit the module — silkscreen says `MODULE PIN 1 AT TOP`. Then flash the production
firmware in `../fw`, which has never run on hardware.

Check in order: link LED on the RJ45, ARP/ping from the Pi, then DDP frames.

---

## What this cannot test on batch 1

- **All twelve outputs at once.** Nine of them need one jumper each; driving them
  simultaneously through nine flying leads is not a meaningful test of anything.
- **Full-column current.** That is a power test, not a board test — see the power
  riser sheet.

Both clear the moment a devkit seats on both rows: either batch 2 at 25.4 mm, or a
devkit soldered in a batch-1 board used as a jig (FABRICATION.md).

---

## Fault table

| Symptom | Look at |
|---|---|
| Step 1 pegs the current limit immediately | J13 polarity; C1–C4 orientation; Q1; a bridge under U1/U2 |
| No 3.3 V at M2 pin 2 | U3 and its input/output caps |
| /OE stays at 3.3 V after flashing | A1L pin 12 not contacting — re-seat the left row |
| Devkit dead with board powered, no USB | A1L pins 21/22 not contacting |
| Panel dark, heartbeat fine, /OE low | U1 legs not formed; U1 pin 1 backwards; panel power; DIN on the round pad instead of the square one |
| Brief garbage on the panel at power-up | Normal. R16–R27 park DIN low until the firmware enables the buffers |
| One output dead, its neighbours fine | That R*n*, or that socket pin — re-run the step 0.3 sweep on it |
| Far end of a panel dim or orange | Voltage drop, not dead LEDs. Feed the panel at both ends |
