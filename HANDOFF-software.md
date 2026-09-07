# Baybasi pixel wall — software handoff

Build the software for a WS2812B video wall whose hardware is already designed,
ordered and specified. Nothing in this document is open for redesign; the
electrical and topology decisions are settled and the boards are in fabrication.
What does not exist yet is any software at all.

## What to build

1. **The driver.** Runs on a Raspberry Pi. Decodes media, maps it onto the wall,
   and streams pixels to four controller boards over Ethernet at 30 fps.
2. **The upload utility.** Lets a non-technical person put media on the Pi from a
   laptop or phone, order it into a playlist, and see what the wall will show.
3. **The controller firmware.** Runs on each ESP32-S3. Receives pixel data and
   drives twelve WS2812B panels in parallel. Treat this as in scope: nothing
   works without it, and the pin map below is final.

## The system this plugs into

There are **two physically separate displays**. They share no cable, no ground
and no clock. Each is a complete independent system:

| Per display | Count |
|---|---|
| Raspberry Pi 3 or newer, Pi OS Lite, headless | 1 |
| 8-port unmanaged switch | 1 |
| Controller board, one per panel column | 4 |
| 16×16 WS2812B panel | 48 |

Each controller board is an ESP32-S3-DevKitC-1 with a WIZnet W5500 Ethernet
module on SPI and two SN74AHCT245N level shifters. It has **twelve parallel data
outputs, one per panel**. Panels are never daisy-chained. That is what holds a
strand to 256 LEDs and the frame time to 8 ms.

## Geometry

A display is **64 pixels wide by 192 tall, portrait**. Four columns of panels
across, twelve rows down.

- Column `c` in 0..3 covers `x = c*16 .. c*16+15`. Controller `c` drives it.
- Row `r` in 0..11 covers `y = r*16 .. r*16+15`. Output `D(r+1)` drives it.
- Within a panel, the chain is **column-serpentine**, verified against the
  team's earlier code:

```python
# x, y are 0..15 within the panel
local = x * 16 + (y if x % 2 == 0 else 15 - y)
```

Put the row-to-output assignment and the panel chain order in **YAML, not code**.
It will be wrong somewhere on the first build and you will want to fix it by
editing data at 2 a.m., not by editing Python.

## Pixel format

WS2812B is 24-bit **GRB**, most significant bit first. There is no intensity or
global brightness byte; that is APA102 and this is not that. Brightness is
arithmetic you do before transmission.

Timing, which sets the ceiling and is not negotiable:

| | |
|---|---|
| Bit period | 1.25 µs |
| Per LED | 30 µs |
| 256-LED strand | 7.68 ms |
| Latch | 300 µs budget, covers both the 50 µs and 280 µs part variants |
| **Frame floor, one strand** | **7.98 ms, so 125 fps** |
| **Target** | **30 fps** |

All twelve outputs run simultaneously, so a board's frame time is one strand's,
not twelve.

## Wire protocol

**DDP over UDP, port 4048.** Not Art-Net, not E1.31. Chosen and settled.

- The Pi holds all geometry. A controller knows only how many bytes it owns and
  where they go on its twelve outputs. All four controllers run identical
  firmware and differ only by IP address.
- Each controller owns 3072 pixels, which is 9216 bytes.
- **Payload must not exceed 1472 bytes.** The W5500 does not fragment IP. Use
  480 pixels per packet: 1440 bytes of data plus a 10-byte DDP header is 1450.
- Send a **broadcast PUSH** to latch all four controllers on the same frame.
  Latching per-controller tears visibly at the column seams.
- The controller **double-buffers and latches only complete frames.** A torn
  frame must be dropped, not shown.
- After **500 ms with no packets**, the controller fades to black. A frozen wall
  looks like working content and hides the fault.

Aggregate bandwidth per display is about 8.8 Mbps, so 100 Mbit is ample.

## Network

- Both displays use the **identical subnet, 192.168.50.0/24**. They never see
  each other, so there is no conflict.
- Pi is `.1`. Controllers are `.11` through `.14`, static, held in NVS and set
  at commissioning rather than compiled in. See **Board identity** below.
- Set `ipv4.never-default yes` on the Pi's wired interface. The LED network must
  not become the default route.
- Wired only. No WiFi anywhere in the pixel path.

## Keeping the two displays in step

**No messages pass between the displays.** Both Pis run NTP and derive the same
frame from wall-clock time:

```python
frame_index = int((time.time() - EPOCH) * FPS) % n_frames
```

`EPOCH` is a fixed constant compiled into both. This means **the media set on
both Pis must be byte-identical**, including playlist order. The upload utility
has to make that easy and has to make divergence visible.

## Deliverable 1: the driver

Runs on the Pi. Python is fine; NumPy for the pixel pipeline.

- Decode JPG, PNG, GIF and video. GIF and video both become frame sequences.
- Scale to 64×192. The wall is tall and narrow and most source media is not, so
  make the fit policy configurable per item: letterbox, crop, or stretch.
- Apply gamma then brightness in 16-bit, then dither down to 8-bit. Banding on a
  large dim wall is the most common way this looks cheap.
- Slice into four column spans, pack each into DDP packets, send, broadcast PUSH.
- Pace to 30 fps against a monotonic clock, not `sleep(1/30)`.
- Report achieved fps and dropped frames. Log when the pipeline cannot keep up
  and say which stage was slow.
- **Ship a test-pattern generator.** Panel ID overlay, per-strand colour
  identification, and a vertical white line scrolling horizontally. That last
  one is the pattern that reveals tearing between columns, and you will use it
  more than anything else.

## Deliverable 2: the upload utility

Runs on the Pi. The Pi is headless, so this is a small web app reachable from a
laptop or phone on the same network.

- Accept JPG, PNG, GIF and video. Validate on upload, do not fail at playback.
- List, delete, reorder into a playlist. Set the per-item fit policy and duration.
- **Preview what the wall will actually show**, rendered at 64×192 through the
  same scaling and gamma path as the driver. Someone will upload a landscape
  photo and needs to see the crop before it is eight feet tall.
- Tell the driver to reload without a restart.
- Because the two displays are network-isolated from each other, the same media
  must be uploaded to each Pi in turn. Make that a first-class flow and show a
  checksum or manifest so a mismatch between the two walls is obvious.

## Deliverable 3: the controller firmware

Arduino framework or ESP-IDF, your call.

**Final pin map.** These came from the board's pad coordinates and are not
suggestions:

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

Two things that will otherwise cost you a day:

- **The ESP32-S3 has only four RMT transmit channels.** Twelve parallel outputs
  must use the LCD_CAM peripheral in parallel mode, which is what FastLED's
  ESP32-S3 I2S driver and I2SClocklessLedDriver use. Any GPIO works because it
  routes through the GPIO matrix.
- **GPIO 8 drives /OE and is pulled up to 3.3 V on the board.** High means the
  shifters are high-impedance and the panels see a defined low through the
  output pull-downs. Hold it high through boot and drive it low only once the
  first complete frame is buffered. Otherwise the wall shows noise at power-up.

Ethernet brings up with `ETH.begin(ETH_PHY_W5500, ...)` on arduino-esp32 core
3.x. Wait 50 ms after releasing RST before touching SPI.

## Getting firmware onto the boards

**First flash is over USB, on the bench, before the devkits are seated.** Each
ESP32-S3-DevKitC-1 has a USB-C port with a USB-to-UART bridge; esptool,
PlatformIO or the Arduino IDE all work. Flash all ten in one sitting before any
of them goes into a controller. Two traps: many USB-A to USB-C cables are
charge-only and make the port look dead, and a devkit seated in a board with USB
live will back-feed 5 V out through the power terminal and try to power the
panel column. Bench flashing avoids both.

**Everything after that is over Ethernet, pushed from the Pi.** The boards end
up mid-column, inside enclosures, behind panels, and the enclosure has no USB
opening. Build OTA in from the start, serve the image from the Pi, and make the
driver able to report each controller's running firmware version.

**Recovery is to pull the devkit.** It sits in sockets precisely so a bricked
OTA or a dead chip is a swap rather than a rework.

### Board identity

All four controllers run the same image, so something has to tell a board which
column it owns. Do not solve this by building four firmware images; that turns
every OTA into an opportunity to put column 3's code on column 1.

Recommended: identity lives in NVS, not in the image. A board with no assignment
comes up, takes a link-local or DHCP address, and announces itself with its
factory MAC, which is unique per chip. You assign it a column once, it persists,
and OTA never touches it. Set the W5500's MAC from the same factory MAC so the
two identities cannot drift apart.

The Pi keeps the MAC-to-column table, which is consistent with the Pi holding
all the other geometry. Commissioning a replacement board is then: plug it in,
see the unassigned MAC appear, tell it which column it is.

## Decided already — do not reopen

One panel per output. Pi holds geometry, controllers hold byte counts. DDP over
UDP. Wired Ethernet only. Gamma and brightness on the Pi. Two fully independent
systems synchronised by wall clock. Panel power is injected separately and never
routes through a controller board.

## Where to start

- Prior art from the team, and the source of the panel mapping:
  https://github.com/chanchal1987/baybasi_panel_2025
- Board design, pin map and fabrication notes: `hw/` in this repo, especially
  `hw/FABRICATION.md`.
- **Build a software DDP sink first.** A script that listens on 4048 and renders
  received frames to a window or a PNG. It lets the driver and the utility be
  finished and demoed before a single board arrives, and it is the only way to
  debug mapping bugs without staring at eight feet of LEDs.
