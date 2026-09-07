# Baybasi controller firmware

One image for all four boards. ESP32-S3-DevKitC-1, W5500 on SPI, twelve
parallel WS2812B outputs through two SN74AHCT245N level shifters.

```bash
pio run                      # build
pio run -t upload            # first flash, over the devkit's USB-C, on the bench
pio device monitor
```

Then everything after the first flash goes over Ethernet, from the Pi:

```bash
baybasi ota .pio/build/baybasi-ctrl/firmware.bin --pi-ip 192.168.50.1
```

## Flash all ten before any of them goes into a board

Two traps, both of which cost a day if you meet them mid-assembly:

- **Many USB-A to USB-C cables are charge-only** and make the devkit's port look
  dead. If nothing enumerates, change the cable before you change anything else.
- **A devkit seated in a board with USB live back-feeds 5 V** out through the
  power terminal and tries to power the panel column. Flash on the bench, before
  the devkits are seated. If you must flash a seated devkit, do it with the LED
  PSU on, or with the panel supply disconnected.

Recovery from a bricked OTA is to pull the devkit out of its sockets and put
another one in. That is what the sockets are for.

## Pin map

Final, from the board's pad coordinates. `src/config.h`.

| Function | GPIO |
|---|---|
| W5500 CS / MOSI / SCK / MISO | 10 / 11 / 12 / 13 |
| W5500 INT | 14 |
| W5500 RST | 15, active low |
| LED outputs D1, D2, D3 | 4, 5, 6 |
| LED outputs D4 … D12 | 1, 2, 21, 38, 39, 40, 41, 42, 47 |
| Level-shifter /OE, both chips | 8 |
| Sync input, optional, unpopulated | 7 |
| Status RGB LED | 48 |

## The three things that will otherwise cost you a day

**Twelve outputs cannot use RMT.** The ESP32-S3 has four RMT transmit channels.
Twelve parallel outputs go through the LCD_CAM peripheral in parallel mode,
which is what `I2SClocklessLedDriver` does. Any GPIO works, because it routes
through the GPIO matrix.

**GPIO 8 is /OE and is pulled up to 3V3E on the board.** HIGH means the shifters
are high-impedance and every panel sees a defined low through R16-R27. The
firmware holds it high through boot and drives it low only once the first
*complete* frame has been buffered and clocked out. Skip that and the wall
shows noise at power-up.

**The W5500 needs 50 ms after RST is released before SPI.** `net.cpp` does the
reset itself and waits, then passes `rst = -1` to `ETH.begin` so the driver does
not pulse it again and skip the wait.

## Order of events at power-up

1. `/OE` stays HIGH. Nothing on the wall lights up.
2. Ethernet comes up. Static address from NVS if this board has a column; DHCP
   (in practice link-local) if it does not, which is enough to be seen and
   commissioned and not enough to be mistaken for a working column.
3. The first complete DDP frame is buffered and clocked out.
4. `/OE` goes LOW and the wall becomes visible.

## Board identity

All four boards run the same binary, so something has to say which column a
board owns. That something is NVS, not the image — building four images turns
every OTA into an opportunity to put column 3's code on column 1.

An unassigned board broadcasts an announcement every two seconds on UDP 4049
carrying its factory MAC, which is unique per chip. The W5500's MAC is that same
factory MAC, so the identity on the wire and the identity in the announcement
cannot drift apart. The Pi holds the MAC-to-column table, consistent with the Pi
holding all the other geometry.

Commissioning a replacement board:

```bash
baybasi discover                   # watch the new MAC appear
baybasi assign aa:bb:cc:dd:ee:ff 2 # it reboots onto 192.168.50.13 and stays there
```

Or the same two steps in the upload utility's **Controllers** panel, which also
has a **Find** button that flashes the board's status LED — useful when the
board is behind a panel, mid-column, and you need to know which one it is.

## Frame handling

The board owns 9216 bytes and knows nothing else about the wall. Seven data
packets arrive per frame; one zero-length broadcast PUSH latches all four
controllers together.

Completeness is tracked as a set of byte intervals, not a byte count — a
duplicated packet must not be mistaken for a complete frame. An incomplete
frame at PUSH is counted and **dropped**, never shown.

Three buffers, not two. A frame takes 7.98 ms to clock out and the LED
peripheral reads its buffer by DMA the whole time; with two buffers a latch
arriving mid-transmission hands the network thread the buffer still being
clocked out. The writer, the frame waiting, and the frame being shown are always
distinct, with no lock on the receive path.

After 500 ms with no packets the board fades to black over 600 ms. A frozen wall
looks like working content and hides the fault.

## Status LED

The only thing you can see once the board is in an enclosure behind a panel.

| | |
|---|---|
| red | booting |
| red, blinking | no Ethernet link |
| amber | link up, no pixels for over 500 ms |
| blue | receiving, outputs still disabled |
| green, breathing | running |
| magenta | frames are arriving incomplete |
| white, pulsing | OTA in progress |
| white, flashing | "Find" from the Pi |
| red, fast | fault — read the serial log |

## Colour order

The Pi sends RGB; this firmware reorders to GRB on the way into the strand
buffer (`LED_ORDER_GRB` in `config.h`). If your build of the LED library *also*
reorders, the two swaps cancel and red and green come out exchanged. Set
`LED_ORDER_GRB` to 0 and rebuild.

`baybasi pattern bars` on the Pi settles it in one look: the top band is red.

## Tests

The frame assembler is the part most likely to be subtly wrong, and it is pure
logic, so it compiles and runs on a host:

```bash
clang++ -std=c++17 -O1 -g -fsanitize=thread -I test/shim \
    -o /tmp/fwtest test/test_framebuf.cpp src/framebuf.cpp && /tmp/fwtest
```

That covers out-of-order and duplicated packets, a lost packet leaving the frame
incomplete, the RGB-to-GRB reorder across packet boundaries, and a two-thread
stress test of the triple buffer under ThreadSanitizer.

## Not yet run on hardware

The boards are in fabrication. Everything above is written against the
datasheets, `hw/FABRICATION.md` and the arduino-esp32 3.x API; the frame logic
is tested on a host, but nothing here has been flashed. The first three things
to check on the bench, in order:

1. Serial output shows the factory MAC and `ETH.begin` succeeding.
2. `baybasi discover` on the Pi sees the announcement.
3. `baybasi pattern bars` — panels light, red at the top, no flicker at
   power-up.
