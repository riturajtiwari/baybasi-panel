#!/usr/bin/env python3
"""Flash a run of devkits, one after another, with ONE image.

    ~/.platformio/penv/bin/python3 flash_fleet.py          # from fw/

Builds once, then waits. Plug a devkit in: if it is factory-fresh it says so
and waits for the BOOT dance; otherwise it flashes the image, reads the board's
identity line back over serial, prints one row, and waits for the next.
Ctrl-C ends the run.

Every board gets the same bytes. Each upload is a plain `pio run -t upload`,
whose build is incremental - unchanged source compiles nothing and leaves
firmware.bin as it was - and the image's SHA-256 is checked after every board,
so an edit made mid-run is caught rather than silently shipped to half the
fleet. NOT `-t nobuild`: on this platform that skips assembling the bootloader
and partition images, and esptool's write-flash then refuses its own command
line ("Must be pairs of an address and the binary filename").

macOS only: it watches the USB bus through ioreg. Needs pyserial, which
PlatformIO's own Python already has.
"""
import glob
import hashlib
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time

import serial

HERE = os.path.dirname(os.path.abspath(__file__))
PIO = shutil.which("pio") or os.path.expanduser("~/.platformio/penv/bin/pio")
BIN = os.path.join(HERE, ".pio", "build", "baybasi-ctrl", "firmware.bin")
DEMO_PID = 0x4001     # factory RGB demo on TinyUSB: esptool cannot reset it
JTAG_PID = 0x1001     # USB-Serial/JTAG: the ROM, or this firmware running


def espressif():
    """(pid, serial) of the Espressif device on the bus, or None."""
    out = subprocess.run(["ioreg", "-a", "-r", "-c", "IOUSBHostDevice", "-l"],
                         capture_output=True).stdout
    try:
        root = plistlib.loads(out)
    except Exception:
        return None

    def walk(n):
        if isinstance(n, dict):
            if n.get("idVendor") == 0x303a and n.get("idProduct"):
                yield n
            for c in n.get("IORegistryEntryChildren", []) or []:
                yield from walk(c)
        elif isinstance(n, list):
            for c in n:
                yield from walk(c)

    for d in walk(root):
        return d.get("idProduct"), d.get("USB Serial Number") or ""
    return None


def image_hash():
    with open(BIN, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def port():
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    return ports[-1] if ports else None


def identity_line(timeout=14.0):
    """The first 'col=... src=... want=...' summary the board prints."""
    s, t0 = None, time.time()
    while s is None and time.time() - t0 < 8:
        p = port()
        if p:
            try:
                s = serial.Serial()
                # HWCDC streams only once the host asserts DTR.
                s.port, s.baudrate, s.timeout, s.dtr = p, 115200, 0.3, True
                s.open()
            except Exception:
                s = None
        if s is None:
            time.sleep(0.3)
    if s is None:
        return None
    buf, t0 = b"", time.time()
    try:
        while time.time() - t0 < timeout:
            buf += s.read(512)
            m = re.search(rb"col=(-?\d+) src=(\w+) want=([\d.a-z]+) ip=([\d.]+) cable=(\w+)", buf)
            if m:
                return {k: v.decode() for k, v in
                        zip(("col", "src", "want", "ip", "cable"), m.groups())}
    finally:
        s.close()
    return None


def main():
    print("building once ...", flush=True)
    b = subprocess.run([PIO, "run"], cwd=HERE, capture_output=True, text=True)
    rev = re.search(r"baybasi fw git revision: (\S+)", b.stdout)
    if b.returncode != 0:
        print(b.stdout[-2000:], b.stderr[-2000:])
        sys.exit("build failed")
    rev = rev.group(1) if rev else "?"
    want = image_hash()
    print(f"image built from {rev}, sha256 {want}" +
          ("   WARNING: uncommitted source - every board will say -dirty"
           if rev.endswith("-dirty") else ""), flush=True)
    print("\nplug in a devkit. Ctrl-C when the run is done.\n", flush=True)

    done, last = {}, "start"
    try:
        while True:
            dev = espressif()
            if dev != last:
                last = dev
                if dev and dev[0] == DEMO_PID:
                    print("factory-fresh devkit: hold BOOT, unplug, replug, "
                          "release BOOT", flush=True)
            if dev and dev[0] == JTAG_PID and dev[1] and dev[1] not in done:
                mac = dev[1].lower()
                time.sleep(1.0)
                print(f"{mac}: flashing ...", flush=True)
                r = subprocess.run([PIO, "run", "-t", "upload",
                                    "--upload-port", port()],
                                   cwd=HERE, capture_output=True, text=True)
                if image_hash() != want:
                    print(f"{mac}: STOP - the image changed during the run "
                          f"(source edited?). This board did not get the same "
                          f"bytes as the others.", flush=True)
                    sys.exit(3)
                if r.returncode != 0:
                    print(f"{mac}: UPLOAD FAILED - unplug, replug and it will "
                          f"retry\n" + "\n".join(r.stdout.splitlines()[-6:]))
                    done[dev[1]] = None          # do not hammer a failing board
                    continue
                time.sleep(1.0)
                ident = identity_line()
                done[dev[1]] = ident
                if ident:
                    print(f"{mac}: OK  column {ident['col']} ({ident['src']}) "
                          f"-> {ident['want']}   cable {ident['cable']}   "
                          f"[{rev}]", flush=True)
                else:
                    print(f"{mac}: flashed, but no identity line within 14 s - "
                          f"check it by hand", flush=True)
                print("swap in the next devkit.", flush=True)
            if dev is None and last is None:
                # Bus empty: let a failed board be retried once it is replugged.
                for k in [k for k, v in done.items() if v is None]:
                    del done[k]
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    ok = {k: v for k, v in done.items() if v}
    print(f"\n{len(ok)} board(s) flashed with {rev}:")
    for mac, ident in ok.items():
        print(f"  {mac.lower()}  column {ident['col']}  {ident['want']}")
    cols = [v["col"] for v in ok.values()]
    dupes = sorted({c for c in cols if cols.count(c) > 1})
    if dupes:
        print(f"  NOTE: column(s) {', '.join(dupes)} set on more than one board. "
              f"Fine across two walls; on ONE wall they would collide.")


if __name__ == "__main__":
    main()
