#!/usr/bin/env python3
"""Build JLCPCB's CPL straight from the board, and cross-check it against the BOM.

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 make_cpl.py

Two things KiCad's own position export gets wrong for JLCPCB, both seen in
their placement preview on 2026-09-07:

1. Position. KiCad reports the footprint anchor, which for headers, DIP
   sockets, terminal blocks and radial capacitors is pin 1, not the centre.
   JLCPCB centres the part on the coordinate, so a 1x22 socket landed 27 mm
   off its pads. We report the centre of the pad bounding box instead.

2. Rotation. JLCPCB's zero orientation is their library's, not KiCad's. The
   offsets below were read off their overlay for the exact parts ordered:
   SOT-223 and SOT-23 are 180 out, DIP sockets and pin sockets are drawn
   horizontally at 0, radial caps and 0805s agree.

Mounting holes have no part, so they are dropped. Every designator in
jlcpcb-bom.csv must appear in the CPL and vice versa, or JLCPCB's importer
rejects the BOM with "designators don't exist in the CPL".
"""
import csv, re, sys
import pcbnew

# (footprint-name regex, degrees to ADD to KiCad's rotation, counter-clockwise)
ROT_FIX = [
    (r'^SOT-223',            180),
    (r'^SOT-23',             180),
    (r'^DIP-',               270),   # JLC: pins horizontal, pin 1 bottom-left
    # Same DIP-8 body as the sockets above. Unlike every other entry here this
    # one started as an analogy rather than a reading off JLCPCB's overlay, so
    # it was checked in their placement preview before confirming the rev B
    # order (W2026092200361486, 2026-09-22): VERIFIED CORRECT. SW1 renders with
    # the part's own 1/2/3/4 running top-to-bottom against the board silkscreen
    # 1/2/SP/SP and ON toward the GND pads, i.e. pole 1 = pad 1 = COL_B0 = top
    # slider. A 180 error would have mapped pads 1-4 onto 5-8, wiring
    # COL_B0/B1/SP0/SP1 straight to GND and leaving the switch connecting GND
    # to GND: not damaging, but dead, and confusing to debug.
    (r'^SW_DIP_',            270),
    (r'^PinHeader_1x',       270),   # JLC: horizontal, pin 1 left
    (r'^TerminalBlock_',       0),   # KF350 / KF128: entry on +y at 0, like KiCad's
    (r'^CP_Radial_',           0),   # + on the left at 0, like KiCad's
    (r'^L_Bourns_SRN6045',     0),
    (r'^[RC]_0805',            0),
]
NOT_PLACED = {'J14'}                 # optional sync header: footprint only

def fix_for(fpname):
    for pat, deg in ROT_FIX:
        if re.match(pat, fpname):
            return deg
    print(f'!! no rotation rule for {fpname}, assuming 0')
    return 0

b = pcbnew.LoadBoard('baybasi-ctrl.kicad_pcb')
rows = []
for f in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    ref = f.GetReference()
    if ref.startswith('H'):
        continue
    xs, ys = [], []
    for pd in f.Pads():
        bb = pd.GetBoundingBox()
        xs += [bb.GetLeft(), bb.GetRight()]; ys += [bb.GetTop(), bb.GetBottom()]
    cx, cy = (min(xs) + max(xs)) / 2e6, (min(ys) + max(ys)) / 2e6
    fpname = f.GetFPIDAsString().split(':')[1]
    rot = (f.GetOrientationDegrees() + fix_for(fpname)) % 360
    side = 'Top' if f.GetLayer() == pcbnew.F_Cu else 'Bottom'
    # KiCad's own export negates Y (y-up convention); keep that so the file
    # matches what JLCPCB already accepted for this board's Gerbers.
    rows.append((ref, f'{cx:.4f}', f'{-cy:.4f}', side, f'{rot:.1f}'))

with open('jlcpcb-cpl.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    w.writerows(rows)
cpl = {r[0] for r in rows}

bom = set()
for r in csv.DictReader(open('jlcpcb-bom.csv')):
    bom |= {d.strip() for d in r['Designator'].split(',') if d.strip()}
missing, extra = sorted(bom - cpl), sorted(cpl - bom)
print(f'CPL: {len(cpl)} placements   BOM: {len(bom)} designators   not placed: {sorted(NOT_PLACED)}')
if missing or extra:
    print('!! BOM designators not on the board:', missing)
    print('!! board designators not in the BOM:', extra)
    sys.exit(1)
print('BOM and CPL agree')
for r in rows:
    if r[0] in ('A1L', 'M1', 'U1', 'U3', 'Q1', 'C1', 'J1', 'J7', 'J13', 'L1', 'R1'):
        print('  ', r)
