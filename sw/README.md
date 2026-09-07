# Baybasi wall software

Driver, upload utility and software DDP sink for a 64 x 192 WS2812B wall, per
`../HANDOFF-software.md`. The controller firmware is in `../fw`.

Everything here runs today, against the software sink, with no hardware.

```bash
python3 -m venv .venv && .venv/bin/pip install -e .   # needs ffmpeg on PATH
.venv/bin/baybasi check                               # validate the wall config

# terminal 1 - pretend to be all four controllers
.venv/bin/baybasi sink --bind 127.0.0.1
#   -> http://localhost:8088

# terminal 2 - drive them
.venv/bin/baybasi pattern scroll --target 127.0.0.1
```

`scroll` is the pattern you will use more than any other: a single white column
sweeping across the wall. If the four controllers ever latch at different
times, the line breaks at the column seams and nothing else shows that.

## What is here

| | |
|---|---|
| `baybasi/ddp.py` | the wire format, and the rules that go with it |
| `baybasi/geometry.py` | `wall.yaml` -> per-controller index arrays |
| `baybasi/pixels.py` | gamma, brightness, dither, pack/unpack |
| `baybasi/media.py` | ffmpeg decode and the frame cache |
| `baybasi/library.py` | playlist, timeline, manifest |
| `baybasi/driver.py` | the 30 fps loop |
| `baybasi/sender.py` | packetise, send, broadcast PUSH, wall-clock pacing |
| `baybasi/sink.py`, `sinkweb.py` | the software controller and its viewer |
| `baybasi/patterns.py` | test patterns |
| `baybasi/webapp.py`, `web/` | the upload utility |
| `baybasi/control.py` | discovery, commissioning, OTA |
| `config/wall.yaml` | **all** the geometry |
| `deploy/` | systemd units and a Pi installer |

## Commands

```
baybasi check                          validate the config, print the wire budget
baybasi sink [--out web|ansi|png]      software DDP controller + viewer
baybasi pattern <name> [--target IP]   send a test pattern
baybasi driver [--pattern <name>]      run the wall
baybasi web                            the upload utility
baybasi add FILE...                    add media from the command line
baybasi playlist                       show the compiled timeline
baybasi manifest [--compare other.json]  print or diff the manifest
baybasi discover                       watch for controllers announcing themselves
baybasi assign MAC COLUMN              commission a board
baybasi ota IMAGE [--mac ...]          push firmware over Ethernet
baybasi status                         what the running driver reports
baybasi render --pattern id            render frames to PNG, no network at all
```

Patterns: `id` `strand` `scroll` `chase` `bars` `gray` `solid`.

## The wall config

`config/wall.yaml` holds the whole geometry: panel chain, row-to-output map,
per-panel rotation, addresses, gamma, brightness, epoch. It is data because it
*will* be wrong somewhere on the first build, and you will want to fix it by
editing a file at 2 a.m. rather than editing Python.

The chain is expressed as `axis`/`start`/`serpentine` rather than a hard-coded
formula. The defaults reproduce the team's verified mapping exactly, and a test
asserts that against `local = x * 16 + (y if x % 2 == 0 else 15 - y)`.

Row 7 of column 2 showing row 8's picture is a two-line edit in `panels:`.
A panel mounted upside down is `transform: rot180` on that row.

## Bring-up order

1. `baybasi check` - config valid, every pixel driven exactly once, 8.92 Mbps.
2. `baybasi sink` in one terminal, `baybasi pattern id --target 127.0.0.1` in
   another. Every panel should be captioned with its own column and row.
3. `baybasi pattern chase` - the comet must walk the serpentine smoothly. A
   zig-zagging comet means the chain spec is wrong.
4. With boards: `baybasi discover`, then `baybasi assign <mac> <column>` for
   each. They keep the assignment across OTA.
5. `baybasi pattern bars` - **check red is at the top.** This is the one thing
   the software cannot check for you; see "Colour order" below.
6. `baybasi pattern scroll` - look along the column seams for a broken line.
7. `baybasi web`, upload something, and look at the preview before it is eight
   feet tall.

## Two walls, one media set

The displays share no cable and no clock. Both Pis compute

```python
frame_index = int((time.time() - EPOCH) * FPS) % n_frames
```

so they stay together only if they are playing the *same timeline*. The
playlist therefore compiles to a deterministic frame timeline - an ordered list
of (media, fit, frame count) - and the manifest digest over that timeline is
what you compare between the two Pis.

Upload to each Pi in turn, then on either one open the utility and use
**Compare** with the other's `manifest.json`. Matching digests mean matching
walls. A mismatch is reported in operator terms, not as a hash:

```
$ baybasi manifest --compare /media/usb/pi-b-manifest.json
DIFFERS:
  sunset.jpg: fit letterbox vs crop
  same media, different playlist order
```

`EPOCH` is in `wall.yaml` and must be identical on both Pis. So must the clock:
both run NTP, and `chronyc tracking` is worth a look before you trust the sync.

## Decisions this made that the handoff left open

**Colour order on the wire is RGB, and the firmware reorders to GRB.** The
WS2812B is a GRB part, but that is a property of the LED, not of the link. DDP's
data-type byte declares RGB, so sending GRB while declaring RGB would mislead
Wireshark and any third-party DDP tool. One flag on each side controls it
(`color_order` here, `LED_ORDER_GRB` in the firmware) and *exactly one* of them
must swap. `baybasi pattern bars` tells you which way round you are in one look:
the top band is red.

**Each controller has its own DDP destination id (10-13).** The handoff says the
four boards differ only by IP address, which is still true - the id is derived
from the column, the firmware also accepts the standard id 1 and the broadcast
255, and no byte counts change. It buys two things: one software sink on one
host can stand in for four boards on four addresses, and a packet that arrives
at the wrong board is rejected instead of drawn.

**Media is pre-decoded to raw frames at wall resolution.** A frame is 36 864
bytes; a 30-second clip is 33 MB. The driver then memory-maps and slices instead
of decoding, which is what lets a Pi 3 hold 30 fps with room to spare, and it
makes the two Pis produce byte-identical pixels from byte-identical files.

**Rendering in the sink runs on its own thread.** The first version encoded PNGs
on the receive thread, overflowed the socket buffer, and reported its own
slowness as torn frames from the driver. A debugging tool that lies about the
thing it is debugging is worse than none.

## Performance

Measured on this development machine, per frame, against a 33.33 ms budget:

```
decode 0.08 ms   gamma/dither 0.30 ms   pack 0.88 ms   send 0.33 ms
```

The driver reports these continuously and, when it cannot keep up, names the
slowest stage - because "dropped frames" on its own tells you nothing you can
act on.

## Tests

```bash
.venv/bin/python -m pytest tests -q      # 68 tests, ~12 s
```

They cover the wire rules (payload ceiling, no PUSH on data packets, exactly
seven packets plus one broadcast PUSH per frame), the panel chain against the
team's verified formula, pack/unpack round-tripping, the gamma/dither pipeline,
the playlist timeline and manifest diffing, the upload flows, and a real
driver-to-sink loop over a socket including a deliberately torn frame.

## Installing on a Pi

```bash
sudo IFACE=eth0 PI_IP=192.168.50.1 ./deploy/install.sh
```

That installs to `/opt/baybasi`, puts the library in `/var/lib/baybasi`, sets
the wired interface static with `ipv4.never-default yes` so the LED network
cannot become the default route, enables NTP, and starts both services.
