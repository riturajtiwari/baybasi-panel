# Ask your friend for three things

Copy-paste the block below. It avoids rulers and photographs entirely — both
failed us already, because a 2.54 mm error and a 2.54 mm answer look identical
through a camera.

---

**1 — Row spacing, counted not measured.**

Push the module's pins into a breadboard or a scrap of 0.1-inch perfboard so it
seats fully. Then pick any pin in one row, look straight across at the pin
opposite it in the other row, and **count the empty hole positions between
them.**

Just the number. Don't measure anything.

**2 — Which way does the RJ45 face?**

Hold the module with the pins pointing down and the Ethernet socket facing you.
Are the two pin rows running **left-to-right** across your view, or
**away from you** (front to back)?

**3 — What is it exactly?**

Photograph the silkscreen text on the PCB, or read it out. I need to know
whether it is a genuine WIZnet **WIZ850io** or one of the **W5500 Lite /
USR-ES1** clones — the signal order is identical but the board outlines are not.

---

## What we do with the answers

**Answer 1** gives the spacing exactly. Pin pitch is 2.54 mm by definition, so
if there are *N* empty holes between the rows:

    W5500_ROW_MM = (N + 1) * 2.54

| holes between | spacing | |
|---|---|---|
| 0 | 2.54 mm | the two rows are adjacent — a plain 2×6 header |
| 5 | 15.24 mm | |
| 6 | 17.78 mm | |
| **7** | **20.32 mm** | what `gen_pcb.py` currently assumes |
| 8 | 22.86 mm | same as the ESP32 devkit rows |

Set the constant at the top of `gen_pcb.py`, run `python3 gen_pcb.py`, and the
placement checker re-verifies the whole board. If the new spacing collides with
anything it will say so before the file is written.

**Answer 2** decides the module's rotation on the board, so the RJ45 points off
the left edge instead of into the ground pour.

**Answer 3** is the reason we're asking at all: WIZnet publish the pinout but
not the mechanical spacing, and the clones are not guaranteed to match.

## If they can't get to a breadboard

Second best: calipers **across the two rows, pin centre to pin centre**, and
tell us the number to one decimal. We'll round to the nearest multiple of
2.54 mm — the true value is always one of those.
