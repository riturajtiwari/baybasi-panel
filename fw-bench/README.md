# Bench panel test

Confirm WS2812B panels are alive before any of the real hardware exists. Runs on
a **classic ESP32 devkit** (ESP-WROOM-32, 30-pin, HW-394 or similar), not the
ESP32-S3 the controllers use.

Shares nothing with `../fw` except the serpentine mapping. Different chip,
different pins, no Ethernet. Do not carry pin numbers between them.

## What it does

Chains **4 panels on one wire** (1024 LEDs, one row of the wall) and cycles four
patterns forever. **It runs standalone.** Flash it, unplug the laptop, and it
keeps going: nothing waits on serial and nothing ever finishes.

| # | Pattern | Lit at once | Answers |
|---|---|---|---|
| 1 | **Panel walk**, one panel white | 256 | Is each panel alive, and in what order? |
| 2 | **Band**, a sliding hue-cycling band on every panel | 128 | All panels at once, and every colour channel |
| 3 | **Block**, a quarter panel marching the row in six colours | 64 | Every LED, every colour, at full brightness |
| 4 | **Trace**, one LED end to end | 1 | Exactly which LED does the chain stop at? |


**Nothing ever lights the whole row.** 1024 LEDs at white is ~61 A, which no
bench supply wants, least of all unattended. So the most any pattern lights is
one panel's worth. That is not only safer, it looks better: FastLED scales the
whole frame down to fit the current cap, so lighting less at a time means what
IS lit runs near full brightness.

**The onboard LED blinks at 1 Hz while the firmware is alive.** With no laptop
attached that is your only diagnostic, and it is worth more than it looks:
panels dark but LED blinking means power, data or panels, not a crashed board.

## The two numbers that change on a chain

| | One wire, 4 panels | Production, 12 outputs |
|---|---|---|
| LEDs per wire | 1024 | 256 |
| Frame time | ~31 ms, so ~32 fps | 8 ms, so 125 fps |
| Whole string white | **~61 A** | ~15 A per output |

This rig is a bench convenience. Those two numbers are the whole reason the real
controller gives every panel its own output.

## Powering it standalone

The dev kit needs its own 5 V once the laptop is gone. Two ways:

- **USB phone charger into the USB-C port.** Preferred. It isolates the ESP32
  from LED rail sag, so a heavy moment on the panels cannot brown out the board
  and reset it mid-test. Still tie ESP32 **GND** to panel **GND**.
- **VIN pin from the same 5 V that drives the panels.** One supply, and the
  common ground comes free, but a sagging rail takes the ESP32 down with it.

**Set `SUPPLY_MA` in `src/main.cpp` to what your bench supply can actually
deliver.** It defaults to 5000 mA. FastLED rescales brightness every frame to
stay inside it, so the column comes out dim. That is correct, not a fault.

**Inject 5 V at both ends of the chain.** Twelve panels fed from one end drop a
lot of voltage along the way, and the far panels go dim and orange. That is
voltage drop, not dead LEDs, and it is the most common false alarm on a chain
this long.

## NEVER power a panel from the dev kit

This destroyed a dev kit on 2026-09-13. Read both warnings before you wire anything.

The panel's lead carries three conductors: 5 V, DIN, GND. **Plug all three into the dev
kit and you have made the dev kit the panel's power supply.** Use two of them. Tape off
or pull the 5 V conductor.

256 WS2812B is 15.4 A at white. `SUPPLY_MA` defaults to 5000, so FastLED will happily
scale to a 5 A budget and ask the 5 V pin for it:

| Path                                  | Realistic capability |
|---------------------------------------|----------------------|
| Laptop USB 2.0 port                   | 500 mA               |
| USB 3 port                            | 900 mA               |
| Phone charger                         | 1.5 - 3 A            |
| Dev kit 5 V trace and USB connector   | ~1 - 2 A             |
| What the firmware asks for at default | **5 A**              |

Five to ten times what the path can carry. What burns is the USB connector, the board's
5 V trace or its series protection diode, and the AMS1117 on the same rail.

The production board does not make this mistake: J1-J12 are two-pin, DATA + GND, no
+5 V pin, with 330 ohm in series on every output. Wire the bench the same way.

If you genuinely must run a panel from USB, say so in the build flags. After the
ESP32's own ~50 mA a laptop port leaves about 400 mA, which is seven LEDs at white or
the whole panel at ~2.5 %:

```bash
PLATFORMIO_BUILD_FLAGS="-DPANELS=1 -DSUPPLY_MA=400" pio run -t upload
```

That is enough to prove a panel is alive and nothing more.

## NEVER drive data into an unpowered panel

The WS2812B's DIN pin has an ESD clamp diode to VDD. Drive DIN at 3.3 V while the
panel's 5 V rail is dead and that diode forward-biases, and **your GPIO becomes the
power supply for the whole panel**:

    GPIO 13 -> LED1 DIN -> ESD clamp diode -> the panel's entire 5 V net

An ESP32 pad is rated 40 mA absolute maximum. 256 WS2812B just sitting quiescent is
~256 mA, and at the ~2.6 V a clamp diode passes they are all in brownout, where the
draw is not 256 mA but whatever the half-biased silicon decides. LED 1's diode fails
short, GPIO 13 becomes a dead short to ground, and the AMS1117 on the dev kit
current-limits at about 1 A while dropping 1.7 V. That is the smoke.

**A switched-off supply does not save you. It is the reason it never stops.** An SMPS
with its switch off still has output capacitors and a bleeder resistor between +V and
-V, and -V is tied to your ESP32 ground. The panel's 5 V net therefore has a permanent
path to ground, so the GPIO never charges something up and stops. It sources current
until something fails.

Two rules, both cheap:

1. **One switch for everything.** Panel 5 V comes up before or with the ESP32, and goes
   down after it. Easiest is to power the ESP32 from the same 5 V that feeds the panels.
2. **330 ohm in series with DIN at the ESP32 end. Always, not just when debugging.**
   It caps a repeat of this at 3.3 V / 330 = 10 mA, which the pad shrugs off, and it
   does not measurably soften the edge over a short lead.

If it has already happened: the dev kit is scrap, do not try to rescue it. Test the
panel on a known-good board too — a damaged LED 1 blocks data to everything behind it.

## Wiring

- **330 ohm in series** between **GPIO 13** and **panel DIN**. See above. Not optional.
- **Panel GND** to an ESP32 **GND** pin. Not optional either, and the usual reason a
  column sits dark.
- **No wire, ever, between the dev kit's 5 V or VIN pin and the panel.** The panel's
  5 V comes from the bench supply and only from the bench supply:

      bench supply (ON) --5 V--+-- panel VDD
                               +-- panel GND --+-- ESP32 GND     <- mandatory
      USB -- ESP32 -- GPIO 13 --[330]----------+-- panel DIN
- **Panel 5 V and GND** to the bench supply, at both ends of the chain.
- ESP32 powered from a USB charger, or from VIN — see above.
- Keep the lead to the first panel under about 30 cm.

**Power the panel supply on first, and off last.** Every time.

A phone charger makes a fault worse than a laptop does: a laptop USB port will often
current-limit or shut down, a charger will happily deliver 2 A into a short.

**GPIO 12 is not used and must not be.** Held high at reset it sets the flash
voltage wrong and the board will not boot. On the header it sits between D14 and
D13, so count pins rather than trusting the gap.

### Do not use the blue level shifter

The 4-channel BSS138 board shifts through a MOSFET with 10 k pull-ups. The rising
edge takes hundreds of nanoseconds against a 400 ns data pulse, so it turns clean
data into garbage. It is the part the controller design rejected in favour of the
SN74AHCT245. Drive the first panel straight from the ESP32 at 3.3 V.

3.3 V into a 5 V-powered WS2812B is marginal on paper, since DIN wants
0.7 x VDD = 3.5 V, but it works over a short lead and is how these are normally
bench-tested. Only the first panel sees it; every LED reshapes the signal for the
next one, so a long chain is no harder than a short one. If the first panel
misbehaves:

1. Shorten the data lead.
2. Drop the panel supply to about 4.5 V, which pulls the threshold under 3.3 V.

(The 330 ohm series resistor is already mandatory — see the wiring section.)

## Bringing up the controller board on flying leads

The devkit in hand measures **2.5 mm wider** between its header rows than the
board's A1L/A1R sockets - 25.4 mm against 22.86 mm, which is exactly one 2.54 mm
pitch. It will not seat. **Do not press harder**: the sockets are factory-soldered
and splaying their contacts turns a good board into scrap.

You do not need it seated.

### First try: does the LEFT row alone go in?

At a 2.54 mm mismatch one row often seats while the other rides outboard. If the
left row (A1L) is down, **you need no jumpers at all** - everything the bring-up
firmware touches is on it:

| Devkit pad | GPIO | On this board |
|---|---|---|
| 4, 5, 6 | 4, 5, 6 | LED outputs D1, D2, D3 -> J1, J2, J3 |
| 7  | 7  | sync in |
| 8  | 15 | W5500 RST |
| 12 | 8  | /OE for both 245s |
| 16, 17, 18, 19 | 10, 11, 12, 13 | W5500 CS, MOSI, SCK, MISO |
| 20 | 14 | W5500 INT |
| 21, 22 | - | 5 V in, GND |

**The whole W5500 interface is on that row**, so Ethernet and the production
firmware in `../fw` can be brought up with the devkit half-seated. D4-D12 are all
on the right row and stay dark; they are nine more copies of the circuit D1-D3
already proves.

Three cautions while it sits at an angle:

- **Check the loose row touches nothing.** Those pins sit over U2's socket and
  the output resistors. Slide card or Kapton underneath.
- **Confirm seating in one second:** power from J13 with no USB. If the devkit
  comes up, pads 21 and 22 are making contact.
- **Expect noise on J4-J12.** Their 245 inputs float with the row unseated, so
  the buffers pass garbage to those terminals. Harmless if nothing is connected.

Do not leave a devkit levered like this permanently - the seated pins carry the
bending moment and A1L's contacts take it.

### If neither row seats: three jumpers

Female-to-male Dupont leads: the female end onto the devkit's header pin, the
male end (0.64 mm square) straight into the socket hole. Count holes on **A1L**,
the LEFT socket, from the **TOP** of the board - the J1-J6 terminal-block end,
with the devkit's USB ports toward the bottom edge.

| Devkit pin | A1L hole | Carries |
|---|---|---|
| `GND` (below `5Vin`) | **22**, the last one | the only logic reference. Not optional |
| `8`  | **12** | /OE. LOW or nothing leaves the board |
| `4`  | **4**  | output D1 -> R1 330R -> J1 |

**Check the count before you trust it.** A1L hole 22 is a dead short to the J13
GND terminal, and hole 21 shows a diode drop to J13 `+` through Q1. If those two
do not read that way you are counting from the wrong end, and hole 4 is really
hole 19 (GPIO13) - which will look exactly like a dead board.

Power:

- **Board** from J13, off the bench supply.
- **Devkit** from USB only. Do NOT also jumper 5 V: its 5 V pin back-feeds this
  board through Q1's channel. See FABRICATION.md.
- **Panel 5 V and GND from the bench supply**, never from this board. J1-J12
  carry DATA + GND only, which is exactly why this board cannot repeat the
  dev-kit failure above.
- Panel DIN to J1's **square** pad (`J1-J12: SQ PAD = DATA` on the silkscreen).

```bash
pio run -e ctrl-board -t upload
```

Flash over the **COM** port (the UART bridge). The monitor is on the **USB**
port, because the env sets `ARDUINO_USB_CDC_ON_BOOT=1`.

What lights proves: J13, Q1, the 5 V rail, U3 and the 3V3E rail, R15, U1, R1,
J1 and the full signal chain. What it does not touch: U2 and outputs 7-12, and
the W5500. Add `-DLED_PIN=5` and move the jumper to A1L hole 5 to walk along
D2, D3, and so on.

## Flashing the S3 devkits: expect the BOOT dance

Confirmed on hardware 2026-09-19. These boards have two USB-C ports. The one that
enumerates on macOS as **`/dev/cu.usbmodem*`** is the **native USB-Serial/JTAG**
port, not a UART bridge (a bridge would appear as `cu.wchusbserial*` or
`cu.usbserial-*`). esptool cannot reset a native-USB port into download mode while
application firmware owns it, so a plain upload fails with:

    A fatal error occurred: Failed to connect to ESP32-S3: No serial data received.

Force download mode by hand, every upload:

1. Hold **BOOT**.
2. Tap **RST**.
3. Wait a beat, release **BOOT**.
4. The RGB LED goes dark - that is your confirmation. Wait ~2 s to enumerate.

**Then do NOT pass `--upload-port`.** The device renames itself between application
mode and ROM download mode (seen: `usbmodem1234561` -> `usbmodem101`), so a pinned
port fails with "No such file or directory". Let auto-detect find it:

```bash
ls /dev/cu.* && pio run -e ctrl-all12 -t upload
```

A good upload reports `USB mode: USB-Serial/JTAG` and `Hash of data verified` on
every block. It also prints the **MAC address** - record it, the driver assigns
columns by MAC.

## Build and flash

PlatformIO is not installed by default on this machine:

```bash
uv tool install platformio
```

Plug the devkit in with a **data** USB-C cable first. A charge-only cable is
indistinguishable from a dead board. Check it appeared with `ls /dev/cu.*`,
looking for `/dev/cu.wchusbserial*`. The HW-394 uses a CH340C, which macOS
Sequoia drives natively.

```bash
pio run -t upload && pio device monitor
```

If upload times out, hold **BOOT**, tap **EN**, release **BOOT**, retry.

### If nothing lights at all

Check the chipset before suspecting hardware. These panels are older than the
WS2812B the wall is specified around, and the wrong chipset looks identical to a
dead column. Uncomment one line in `platformio.ini` and reflash:

```
; -DLED_CHIPSET=WS2811
; -DLED_CHIPSET=WS2812
; -DLED_CHIPSET=SK6812
```

### Testing a different number of panels

`PANELS` is a build flag, so no source edit is needed:

```bash
pio run -t upload                                   # 4 panels, one row
PLATFORMIO_BUILD_FLAGS="-DPANELS=1"  pio run -t upload   # a single panel
PLATFORMIO_BUILD_FLAGS="-DPANELS=12" pio run -t upload   # a whole column
```

Every pattern scales itself, and the lit-LED count stays bounded at one panel's
worth regardless, so a column is no harder on the supply than a row.
