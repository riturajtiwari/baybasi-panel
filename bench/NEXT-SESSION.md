# Baybasi — handoff, 2026-09-19

Read `bench/STATE.md` first for the volatile bench state (IPs, the temporary
config hack, what is flashed). The hard-won findings are in memory:
`baybasi-fw-first-run`, `baybasi-fw-first-build`, `baybasi-batch1-bringup`,
`baybasi-power-distribution`, `ws2812-unpowered-panel-kills-gpio`.

## Where it stands

**One controller board is fully validated on hardware.** Power, reverse
protection, both rails, /OE through the socket, U1, the series resistors, the
output terminals, the W5500, Ethernet, DHCP, discovery and DDP.

**Video rate is proven, and at scale.** 40 s of `baybasi pattern flow` -
a pattern where 100 % of pixels change every frame:

    frames=1958  shown=1952  torn=0  gaps=1  malformed=0  oversize=0
    show(): avg 5078 us     heap flat     sender 30.00 fps, 0 send errors

`show()` is **5.08 ms of a 33.3 ms budget - 15 % duty, a ~197 fps ceiling**.
That figure is for **all twelve outputs**: the LCD_CAM driver clocks every lane
in parallel whether a panel is attached or not, so the other nine panels cost
nothing in time. Network is 2.2 Mbps of 100. Twelve panels of 30 fps video is
not a stretch for this board.

**Also proven:** the column-serpentine map (the `bars` pattern renders a
*legible* "1", which validates the 2-D mapping, not just chain order) and the
channel order (`CHANNEL_MAP = {2,0,1}`, measured).

## What to do next, in order

1. **The DHCP gap in `fw/src/net.cpp`.** The highest-value item, and the only
   one that blocks *every* board. There is deliberately no DHCP on the pixel
   segment, so an unassigned board never gets an IP, never announces, and
   cannot be commissioned - it only worked tonight because the home LAN has a
   DHCP server. ~10 lines: give unassigned boards a deterministic address
   derived from the MAC, e.g. `192.168.50.(128 + (mac[5] & 0x3F))`.
2. **Commission this board.** `baybasi assign ae:27:6e:a5:83:8d 0`. Retires the
   `bench/wall-bench.yaml` ddp_id hack. It reboots onto 192.168.50.11, so this
   also means moving to the pixel-segment addressing.
3. **Strip the debug instrumentation from `fw/src/main.cpp`** - loop counters,
   `acquire()` null counter, show() timing. Earned its keep; noise now.
4. **Real media end to end.** `flow` proves synthetic frames; the actual use
   case is video and images through `baybasi add` / `driver`. That exercises
   decode, scaling and the playlist, none of which have touched hardware.
5. **Outputs J4-J12.** Needs both devkit rows, so either the 14 breadboard
   jumpers (table in `hw/BRINGUP.md` step 6) or a devkit with headers soldered
   in the board as a jig.
6. **Batch 2 PCB**: move A1L/A1R to 25.4 mm, and decide the co-routed
   power+data cable question (see the power riser artifact).

## Traps that cost real time tonight

- **Always `pkill -f "baybasi.*pattern"` before any visual test.** A stray
  sender left running by hand sent 7200 frames over four minutes and silently
  interleaved with every colour measurement. "Flashing" or colours that will
  not sit still is exactly what that looks like.
- **Do not reason about the colour chain - measure it.** CHANNEL_MAP ->
  reinterpret_cast to CRGB -> FastLED EOrder -> panel wiring. Predicting that
  composition gave the wrong answer twice.
- **The IDF version is a window, not a floor.** 5.4.x only. `<=5.3` will not
  compile, 5.5 breaks the LCD i80 bus at runtime. Do not "upgrade" the platform
  without re-running the frame-rate test on hardware.
- **Three different MACs.** Commission with the firmware's `ae:27:6e:a5:83:8d`.
- **`firmware.factory.bin` does not exist on the 54.x platform.** Flash four
  images at offsets. A missing file made one flash silently no-op; the tell was
  the panic log's `ELF file SHA256` not changing between builds.

## Uncommitted

Everything from tonight is uncommitted on `master` (last commit `78ec85f`).
Modified: `fw/platformio.ini`, `fw/src/{config,framebuf,leds,main,net,status}`,
`sw/baybasi/{control,patterns}.py`, `hw/FABRICATION.md`, `HANDOFF-software.md`.
New and untracked: `bench/`, `fw-bench/`, `hw/BRINGUP.md`.
**Nothing has been committed - that is deliberate, ask before committing.**
