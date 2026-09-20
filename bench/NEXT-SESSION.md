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

1. ~~**The DHCP gap in `fw/src/net.cpp`.**~~ **DONE 2026-09-19.** A board with
   no address of its own now waits `DHCP_WAIT_MS` (8 s) and then takes
   `192.168.50.<MAC-derived>`. Proven on hardware against a laptop with no
   DHCP server: the board took 192.168.50.125, announced every 2 s, and
   `baybasi discover` listed it as unassigned.

   Two things that were NOT in the original one-line plan:
   - `linkUp()` was `g_link && ETH.linkUp()`, and `g_link` was only ever set
     from `ARDUINO_EVENT_ETH_GOT_IP`. An address the board sets itself raises
     no such event, so the fallback alone would have changed nothing. It now
     reads `ETH.linkUp() && ETH.hasIP()`.
   - The wait is ROLLING, not boot-time. The first version armed once at boot;
     a board that got a lease and then lost it sat at 0.0.0.0 for ever and
     needed a power cycle. That was caught on hardware, not in review.
2. **Commissioning is now usable.** DONE 2026-09-19: `baybasi identify <mac>`
   and `baybasi clear <mac>` exist (both were implemented in ControlPlane and
   unreachable), identify floods the whole column at 2 Hz instead of blinking
   a 2 mm LED inside an enclosure, and a second board can no longer be given a
   column that another board holds. Confirmed on hardware: 12 flashes in 6 s,
   8 in 4 s.

   Install-day plan: commission each board on the BENCH where you can see it
   and put a physical label on it. Keep identify for field recovery - a board
   swapped out, or a label that fell off.

3. **Commission this board.** `baybasi assign ae:27:6e:a5:83:8d 0`. Retires the
   `bench/wall-bench.yaml` ddp_id hack. It reboots onto 192.168.50.11, so this
   also means moving to the pixel-segment addressing.
4. **Strip the debug instrumentation from `fw/src/main.cpp`** - loop counters,
   `acquire()` null counter, show() timing. Earned its keep; noise now.
5. **Real media end to end.** `flow` proves synthetic frames; the actual use
   case is video and images through `baybasi add` / `driver`. That exercises
   decode, scaling and the playlist, none of which have touched hardware.
6. ~~**Outputs J4-J12.**~~ U2 and A1R VALIDATED 2026-09-20 via the step-6
   jumper rig (J4 -> 4 pixels, J7 -> 7). Nothing structural on the PCB is
   unknown now. J8-J12 are individual traces, still untested, one screw
   terminal each if wanted. Original note: Needs both devkit rows, so either the 14 breadboard
   jumpers (table in `hw/BRINGUP.md` step 6) or a devkit with headers soldered
   in the board as a jig.
7. **Batch 2 PCB.** Now a ONE-LINE change: A1L/A1R 22.86 -> 25.4 mm in
   `gen_pcb.py`. The co-routed power+data question is DECIDED 2026-09-20 -
   panel power stays off the board, run separately; see FABRICATION.md. All
   seven defects from the deep QA are already in revA, and U1, U2, A1L and
   A1R are all proven on hardware, so nothing else needs to change.

   Before ordering: record the exact devkit vendor and part number in
   FABRICATION.md. Once the board is cut for 25.4, a reorder that quietly
   ships a different pitch puts you straight back into the socket problem.

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
