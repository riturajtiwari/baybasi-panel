# Bench state — 2026-09-19, end of the first-run session

Volatile things that are NOT in the memory files and will not survive a reboot
or a /tmp clean. Everything durable is in the `baybasi-fw-*` memories.

## The board right now
- **Uncommissioned.** `column=-1`, so `ddp_id` is the default **1**.
- MAC to commission with: **`ae:27:6e:a5:83:8d`** (the firmware's, NOT esptool's
  `ac:...:8c`, NOT the wire's `aa:...:8d`).
- On the **home LAN by DHCP**, last seen **192.168.1.121**. This CHANGES across
  reboots - it was .180 earlier. Never hard-code it; find it with
  `baybasi discover` or by listening on udp/4049.
- On a segment with **no DHCP server** it now takes **192.168.50.125**, derived
  from its MAC and stable across reboots. Any board: the range is .64-.239.
- Firmware: `fw/` built on platform **54.03.21-2** (Arduino 3.2.1 / IDF 5.4.2),
  FastLED S3/I2S, octal PSRAM. Verified 30 fps, shown==frames, colours correct.

## Temporary hacks in force
- **`bench/wall-bench.yaml`** is `config/wall.yaml` with column 0's `ddp_id`
  changed from 10 to **1**, so the UNCOMMISSIONED board accepts data packets.
  Without it every data packet is rejected and only the broadcast PUSH lands
  (`frames=0`, `pkts` climbing). Use `baybasi --config bench/wall-bench.yaml`.
  `--config` is a GLOBAL flag - it goes BEFORE the subcommand.
  Delete this once the board is properly commissioned.
- **Debug instrumentation is still in `fw/src/main.cpp`**: loop-iteration
  counter, `acquire()` null counter, and show() avg/max timing, all reported in
  logSummary. Useful; strip before production.
- Only **J1-J3** are reachable (devkit half-seated in A1L). D4-D12 need the
  breadboard jumpers or a jig-soldered devkit.

## Discovery does not cross to Wi-Fi

`baybasi discover` showed nothing all through the first session, with the
board announcing correctly the whole time. The announce is a limited
broadcast (255.255.255.255), and broadcast does not appear to reach wireless
clients on this network - the UniFi gear filters it. Run the utility from a
machine WIRED to the same segment. Not a problem for the wall, where the Pi is
wired to the pixel segment, but it will waste an afternoon on the bench.

Tested directly: laptop on the monitor's Ethernet port (`en3`, service name
"Display Ethernet"), board straight into it, no DHCP server anywhere. A
TP-Link USB-Ethernet adapter was tried first and never established a link -
suspect that adapter, not the board.

## How to drive it
    pkill -f "baybasi.*pattern"        # ALWAYS - a stray sender ruins every test
    cd sw && .venv/bin/baybasi --config ../bench/wall-bench.yaml \
        pattern <name> --brightness 0.1 --target <ip>

Flash (four images; `firmware.factory.bin` exists only on the 55.x platform):
    esptool.py --chip esp32s3 --baud 460800 write_flash \
      0x0 bootloader.bin 0x8000 partitions.bin \
      0xe000 boot_app0.bin 0x10000 firmware.bin

After a BOOT-dance flash the S3 sits in ROM download mode: silent on serial AND
absent from the network. Neither `esptool --after hard_reset` nor DTR/RTS gets
it out. **Tap RST.**
