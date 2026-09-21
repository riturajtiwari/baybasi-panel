#!/usr/bin/env python3
"""Generate the Baybasi controller PCB: footprints placed, board outline, GND pours.

Placement follows the floorplan: W5500 beside the devkit's SPI pins, the twelve
outputs leaving from the top and bottom edges, power in the corner furthest from
Ethernet. Routing is deliberately left to a human.
"""
import re, uuid, os

STOCK = '/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints'
PCM   = os.path.expanduser('~/Documents/KiCad/10.0/3rdparty/footprints/'
                           'com_github_espressif_kicad-libraries')
HERE  = os.path.dirname(os.path.abspath(__file__))
OUT   = os.path.join(HERE, 'baybasi-ctrl.kicad_pcb')

# --- W5500 module header row spacing: CONFIRMED ------------------------------
# WIZnet omit this from the WIZ850io datasheet (its "Dimension" section is a 3D
# PDF with no numbers). It is stated in the WIZ820io User Manual V1.0, section 5,
# as symbol B = "20.32 (2.54 x 8)". WIZnet specify the WIZ850io as a fully
# pin-compatible replacement for the WIZ820io, and both are 23 x 25 mm with two
# 1x6 headers on 2.54 mm pitch, so the spacing carries over.
#   https://docs.wiznet.io/img/products/wiz820io/WIZ820io_User_Manual_V1.0.pdf
W5500_ROW_MM = 20.32

BX, BY = 100.0, 50.0          # board top-left on the page
BW, BH = 100.0, 95.0          # board size - must stay under 100x100 for the cheap fab tier

U = lambda: str(uuid.uuid4())

# ---------------------------------------------------------------- netlist ----
def load_nets():
    t = open(os.path.join(HERE, 'net.net')).read()
    pin2net, order = {}, []
    for b in re.split(r'\n\t\t\(net\n', t[t.index('(nets'):])[1:]:
        nm = re.search(r'\(name "([^"]*)"', b)
        if not nm:
            continue
        name = nm.group(1).lstrip('/')
        if name not in order:
            order.append(name)
        for ref, pin in re.findall(r'\(ref "([^"]+)"\)\s*\n?\s*\(pin "([^"]+)"', b):
            pin2net[(ref, pin)] = name
    return pin2net, ['', *order]

PIN2NET, NETLIST = load_nets()
NETIDX = {n: i for i, n in enumerate(NETLIST)}

# --------------------------------------------------------------- footprint ---
def fp_text(libname):
    lib, name = libname.split(':')
    if lib == 'baybasi':
        d = os.path.join(HERE, 'baybasi.pretty')
    elif lib == 'PCM_Espressif':
        d = f'{PCM}/Espressif.pretty'
    else:
        d = f'{STOCK}/{lib}.pretty'
    return open(f'{d}/{name}.kicad_mod').read()

def place(ref, libname, rx, ry, rot=0, layer='F.Cu'):
    """Emit a footprint block positioned at board-relative (rx, ry)."""
    t = fp_text(libname).strip()
    inner = t[t.index('\n'):]                       # drop '(footprint "NAME"'
    inner = inner.rstrip()
    assert inner.endswith(')')
    inner = inner[:inner.rindex(')')]
    for tag in ('version', 'generator', 'generator_version', 'layer', 'descr', 'tags'):
        inner = re.sub(r'\n\t\(' + tag + r' [^\n]*\)', '', inner)

    def netify(m):
        pad = m.group(0)
        num = m.group(1)
        net = PIN2NET.get((ref, num))
        if net is None:
            return pad
        idx = NETIDX[net]
        return pad + f' (net {idx} "{net}")'
    # attach the net right after each pad's shape/size block opener
    inner = re.sub(r'\(pad "([^"]+)" \w+ \w+', netify, inner)

    x, y = BX + rx, BY + ry
    inner = re.sub(r'\(property "Reference" "[^"]*"', f'(property "Reference" "{ref}"', inner, count=1)
    if ref in REF_AT:                      # move the label where it stays legible
        ax, ay, ar = REF_AT[ref]
        inner = re.sub(r'(\(property "Reference" "' + re.escape(ref) + r'"\s*\(at )[^)]*\)',
                       lambda m: f'{m.group(1)}{ax} {ay} {ar})', inner, count=1)
    if re.match(r'^[RCH]\d', ref):         # passives, holes: keep the silkscreen clear
        inner = re.sub(r'(\(property "Reference" "' + re.escape(ref) + r'".*?\(layer ")F\.SilkS(")',
                       r'\1F.Fab\2', inner, count=1, flags=re.S)
    if '(property "Reference"' not in inner:
        inner = (f'\n\t\t(property "Reference" "{ref}" (at 0 -1.8 0) (layer "F.SilkS") '
                 f'(uuid {U()}) (effects (font (size 0.8 0.8) (thickness 0.15))))') + inner
    return (f'\t(footprint "{libname}"\n\t\t(layer "{layer}")\n\t\t(uuid {U()})\n'
            f'\t\t(at {x:.3f} {y:.3f}{"" if rot == 0 else f" {rot}"})'
            f'{inner}\n\t)')

# reference-text overrides, footprint-local (x, y, angle)
REF_AT = {
    'A1L': (-3.6, 26.67, 90),   # beside the socket, outside the devkit outline
    'A1R': (3.6, 26.67, 90),
    'J13': (8.7, 0, 0),         # below the block once it is turned 270 deg
    'U1': (-2.4, 11.43, 90),    # left flank of the DIP, clear of the resistor rows
    'U2': (-2.4, 11.43, 90),
    'Q1': (2.9, 0, 90),         # right flank; the default spot collides with J13's
}

# ------------------------------------------------------------------ layout ---
FP = {
    'SW1': 'Button_Switch_THT:SW_DIP_SPSTx04_Slide_9.78x12.34mm_W7.62mm_P2.54mm',
    'R15': 'Resistor_SMD:R_0805_2012Metric',
    'A1L': 'Connector_PinHeader_2.54mm:PinHeader_1x22_P2.54mm_Vertical',
    'A1R': 'Connector_PinHeader_2.54mm:PinHeader_1x22_P2.54mm_Vertical',
    'M1':  'Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical',
    'M2':  'Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical',
    'U1':  'Package_DIP:DIP-20_W7.62mm',
    'U2':  'Package_DIP:DIP-20_W7.62mm',
    'U3':  'Package_TO_SOT_SMD:SOT-223-3_TabPin2',
    'Q1':  'Package_TO_SOT_SMD:SOT-23',
    'L1':  'Inductor_SMD:L_Bourns_SRN6045TA',
    'C1':  'Capacitor_THT:CP_Radial_D10.0mm_P3.50mm',
    'C2':  'Capacitor_THT:CP_Radial_D6.3mm_P2.50mm',
    'C3':  'Capacitor_THT:CP_Radial_D5.0mm_P2.50mm',
    'C4':  'Capacitor_THT:CP_Radial_D5.0mm_P2.50mm',
    'J13': 'TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal',
    'J14': 'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
}
for n in range(1, 13):
    FP[f'R{n}'] = 'Resistor_SMD:R_0805_2012Metric'
    FP[f'R{15+n}'] = 'Resistor_SMD:R_0805_2012Metric'      # OUTn pull-down
    FP[f'J{n}'] = ('TerminalBlock_Phoenix:TerminalBlock_Phoenix_'
                   'PT-1,5-2-3.5-H_1x02_P3.50mm_Horizontal')
for n in range(5, 10):
    FP[f'C{n}'] = 'Capacitor_SMD:C_0805_2012Metric'
FP['R13'] = 'Resistor_SMD:R_0805_2012Metric'
FP['R14'] = 'Resistor_SMD:R_0805_2012Metric'
for n in range(1, 5):
    FP[f'H{n}'] = 'MountingHole:MountingHole_3.2mm_M3'

def courtyard(libname):
    t = fp_text(libname)
    pts = []
    for m in re.finditer(r'\(fp_(\w+)\s*(.*?)\(layer "F\.CrtYd"\)', t, re.S):
        kind, blob = m.group(1), m.group(2)
        p = [(float(a), float(b)) for a, b in re.findall(r'([-\d.]+) ([-\d.]+)\)', blob)]
        if kind == 'circle' and len(p) >= 2:
            (cx, cy), (ex, ey) = p[0], p[1]
            r = ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5
            p = [(cx - r, cy - r), (cx + r, cy + r)]
        pts += p
    pad_only = not pts
    if pad_only:
        pts = [(float(a), float(b)) for a, b in
               re.findall(r'\(pad "[^"]*" \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+)', t)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    if pad_only:
        # no F.CrtYd in the footprint (e.g. the radial inductor): grow the pad
        # extent so the checker never sees a degenerate box
        m = 2.6
        x0, y0, x1, y1 = x0 - m, y0 - m, x1 + m, y1 + m
    return x0, y0, x1, y1


# --- guard: the PCB part list is maintained here, separately from the
# schematic. They drifted once (R13/R14 were in the schematic and absent from
# the board, leaving a floating FET gate and a floating W5500 reset). Never
# again: abort if the two disagree.
_sch = set(re.findall(r'\(comp\s+\(ref "([^"]+)"\)', open(os.path.join(HERE,'net.net')).read()))
_pcb = {r for r in FP if not r.startswith('H')}
_missing, _extra = sorted(_sch - _pcb), sorted(_pcb - _sch)
if _missing or _extra:
    raise SystemExit(f"ABORT: schematic and PCB part lists disagree.\n"
                     f"  in schematic, missing from PCB: {_missing}\n"
                     f"  on PCB, absent from schematic : {_extra}")
print(f'part lists agree: {len(_sch)} components')

CY = {r: courtyard(FP[r]) for r in FP}

# Footprint rotations, KiCad convention: degrees counter-clockwise on screen
# with y pointing down. Both Phoenix blocks have their wire openings on the
# footprint's +y face, so J1-J6 on the top edge are flipped to face outward and
# J13 on the left edge is turned so the PSU leads come in from the left.
ROT = {f'J{n}': 180 for n in range(1, 7)}
ROT['J13'] = 270

def rbox(ref):
    """Courtyard box of ref in board orientation, rotation applied."""
    x0, y0, x1, y1 = CY[ref]
    rot = ROT.get(ref, 0)
    def rt(lx, ly):
        return {0: (lx, ly), 90: (ly, -lx), 180: (-lx, -ly), 270: (-ly, lx)}[rot]
    pts = [rt(*c) for c in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return min(xs), min(ys), max(xs), max(ys)

RB = {r: rbox(r) for r in FP}
POS = {}
def col(x, y0, refs, gap=2.0):
    """Stack refs vertically at x, spacing from their real courtyard heights."""
    y = y0
    for r in refs:
        x0, cy0, x1, cy1 = RB[r]
        POS[r] = (x - x0, y - cy0, ROT.get(r, 0))
        y += (cy1 - cy0) + gap
    return y

def row(y, x0, refs, gap=2.0):
    x = x0
    for r in refs:
        cx0, y0, cx1, y1 = RB[r]
        POS[r] = (x - cx0, y - y0, ROT.get(r, 0))
        x += (cx1 - cx0) + gap
    return x

# top band: six outputs with their openings toward the edge, then the series
# resistors and the pull-downs in one line beneath them. Mirrored at the bottom.
row(1.0,  36.0, [f'J{n}' for n in range(1, 7)], gap=1.2)
row(11.5, 27.5, [f'R{n}' for n in range(1, 7)], gap=0.6)
row(11.5, 51.5, [f'R{n}' for n in range(16, 22)], gap=0.6)
row(81.2, 27.5, [f'R{n}' for n in range(7, 13)], gap=0.6)
row(81.2, 51.5, [f'R{n}' for n in range(22, 28)], gap=0.6)
row(85.0, 36.0, [f'J{n}' for n in range(7, 13)], gap=1.2)

# left band: Ethernet module at the top, power chain beneath it
M1_PIN1 = (4.77, 15.0)                  # pin 1 of the left row, board coords
for _r, _dx in (('M1', 0.0), ('M2', W5500_ROW_MM)):
    POS[_r] = (M1_PIN1[0] + _dx, M1_PIN1[1], 0)
# WIZ850io body, from the WIZ820io UM V1.0 sec.5 drawing: 23 x 25 mm, pin rows
# 1.34 mm in from the long edges (C, G), pin 1 6.4 mm from the RJ45 edge (I),
# and the jack protrudes a further 2.5 mm (H). Kept clear like the devkit body.
W5500_BODY = (M1_PIN1[0] - 1.34, M1_PIN1[1] - 6.4,
              M1_PIN1[0] + W5500_ROW_MM + 1.34, M1_PIN1[1] - 6.4 + 25.0)
RJ45_W, RJ45_OUT = 16.1, 2.5
_yn = col(1.0, 36.0, ['J13'], gap=1.5)             # openings face the left edge
col(3.0, _yn, ['Q1', 'L1', 'C1'], gap=1.5)
col(14.5, 36.0, ['U3', 'C3', 'C4', 'C2'], gap=1.5)
col(26.0, 36.0, ['C7', 'C9', 'C8', 'R13', 'R14'], gap=2.0)
col(11.0, 86.5, ['J14'], gap=1.5)
for _n, (_hx, _hy) in enumerate(((1.2, 1.2), (BW - 7.6, 1.2),
                                 (1.2, BH - 7.6), (BW - 7.6, BH - 7.6))):
    _x0, _y0, _x1, _y1 = RB[f'H{_n+1}']
    POS[f'H{_n+1}'] = (_hx - _x0, _hy - _y0, 0)

# centre: the devkit sits on two 1x22 sockets, pad 1 (3V3) at the top, so its
# USB end points at the bottom edge. Body: 0.85 mm above pad 1, 9.2 mm below
# pad 22 (the USB shells and buttons live there), 1.25 mm outside each pin row.
#
# A1_PITCH was 22.86 through batch 1, which is Espressif's own row spacing for
# the DevKitC-1 (board width 25.40 less 1.27 from each edge to the pin-row
# centreline, from their dimension drawing). It is correct for that part and
# the design was never wrong.
#
# Batch 2 is 25.4 because every devkit actually in hand is a third-party board
# at that spacing - exactly one 2.54 mm pitch wider - and none of them seat in
# a 22.86 socket. Two independent confirmations: the fit test, which is binary
# and cannot be misread, and a hole-centre-to-hole-centre measurement on a
# bare board (2026-09-15).
#
# Do NOT "correct" this back by comparing board WIDTHS. 25.40 is the official
# board's width and 22.86 its row spacing; their difference is also 2.54, so
# mixing the two yields "exactly one pitch" as an artefact and reads like
# confirmation. Measure hole centre to hole centre, on a bare board, or do not
# measure at all. See hw/FABRICATION.md.
A1_PITCH = 25.4
A1_PAD1 = (35.57, 17.0)
POS['A1L'] = (A1_PAD1[0], A1_PAD1[1], 0)
POS['A1R'] = (A1_PAD1[0] + A1_PITCH, A1_PAD1[1], 0)
A1_BODY = (A1_PAD1[0] - 1.25, A1_PAD1[1] - 0.85,
           A1_PAD1[0] + A1_PITCH + 1.25, A1_PAD1[1] + 62.55)
# right: level shifters with their decoupling alongside.
#
# Shifted +2.5 mm for batch 2, together with the socket. A1R moved 2.54 mm
# right when A1_PITCH went to 25.4, which squeezed the A1R-to-U1 channel from
# about 7 mm to 4.5 mm; the router then could not keep the B.Cu pour continuous
# through it and left isolated GND regions around x 60-78, y 24-34. Moving the
# whole right-hand cluster by the same amount restores the channel.
col(71.5, 15.0, ['U1'], gap=2.5)
col(71.5, 45.0, ['U2'], gap=2.5)
col(83.0, 17.0, ['C5'], gap=2.5)
col(83.0, 47.0, ['C6'], gap=2.5)
col(91.0, 30.0, ['R15'], gap=2.5)
# column-select switch: below the devkit's LEFT row, the only clear pocket of
# this size. Pads 1-4 face A1L, which is where COL_B0/B1/SP0/SP1 come from, so
# the four traces are short and do not cross the board.
POS['SW1'] = (24.0, 69.0, 0)

boxes = {}
for r in FP:
    x0, y0, x1, y1 = RB[r]
    px, py, _ = POS[r]
    boxes[r] = (px + x0, py + y0, px + x1, py + y1)

boxes['(devkit body)'] = A1_BODY     # virtual keepouts under the plug-in modules
boxes['(w5500 body)'] = W5500_BODY
clash = []
refs = sorted(boxes)
for i, a in enumerate(refs):
    ax0, ay0, ax1, ay1 = boxes[a]
    EDGE = 0.6
    if ax0 < EDGE or ay0 < EDGE or ax1 > BW - EDGE or ay1 > BH - EDGE:
        clash.append((a, 'OFF-BOARD', round(ax0,1), round(ay0,1), round(ax1,1), round(ay1,1)))
    for b in refs[i+1:]:
        bx0, by0, bx1, by1 = boxes[b]
        if '(devkit body)' in (a, b) and {a, b} & {'A1L', 'A1R'}:
            continue                       # the sockets belong inside their own body
        if '(w5500 body)' in (a, b) and {a, b} & {'M1', 'M2'}:
            continue
        ox, oy = min(ax1,bx1)-max(ax0,bx0), min(ay1,by1)-max(ay0,by0)
        if ox > 0 and oy > 0:
            clash.append((a, b, round(ox,2), round(oy,2)))
if clash:
    print(f'!! {len(clash)} placement conflicts:')
    for c in clash[:25]:
        print('   ', c)
else:
    print('placement clean: no courtyard overlaps, everything on-board')

body = [place(r, FP[r], *POS[r]) for r in FP]


# --- GND stitching vias -------------------------------------------------------
# Tie the two pours together so routing cannot carve the ground plane into
# isolated islands (it did, before these existed). Placed before routing so the
# router treats them as obstacles instead of colliding with them.
_gnd = NETIDX['GND']
_occ = [v for k, v in boxes.items() if not k.startswith('(')]
def _clear(x, y, m=2.2):
    if x < 5 or y < 5 or x > BW - 5 or y > BH - 5: return False
    return all(not (x0-m < x < x1+m and y0-m < y < y1+m) for x0, y0, x1, y1 in _occ)
_stitch = [(x, y)
           for y in [8.0 + 8.5*i for i in range(11)]
           for x in [8.0 + 8.5*j for j in range(11)]
           if _clear(x, y)]
for _sx, _sy in _stitch:
    body.append(f'\t(via (at {BX+_sx:.2f} {BY+_sy:.2f}) (size 0.6) (drill 0.3)'
                f' (layers "F.Cu" "B.Cu") (net {_gnd}) (uuid {U()}))')
print(f'  {len(_stitch)} GND stitching vias')

# --------------------------------------------------------- outline + pours ---
edge = []
pts = [(0, 0), (BW, 0), (BW, BH), (0, BH)]
for i in range(4):
    x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % 4]
    edge.append(f'\t(gr_line (start {BX+x1:.3f} {BY+y1:.3f}) (end {BX+x2:.3f} {BY+y2:.3f})'
                f' (stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid {U()}))')

INSET = 0.5
zpts = ' '.join(f'(xy {BX+x:.3f} {BY+y:.3f})' for x, y in
                [(INSET, INSET), (BW-INSET, INSET), (BW-INSET, BH-INSET), (INSET, BH-INSET)])
gnd = NETIDX['GND']
zone = f'''\t(zone
\t\t(net {gnd}) (net_name "GND")
\t\t(layers "F.Cu" "B.Cu")
\t\t(uuid {U()})
\t\t(name "GND_POUR")
\t\t(hatch edge 0.5)
\t\t(connect_pads (clearance 0.3))
\t\t(min_thickness 0.25)
\t\t(filled_areas_thickness no)
\t\t(fill yes (thermal_gap 0.3) (thermal_bridge_width 0.8))
\t\t(polygon (pts {zpts}))
\t)'''

# --- BayBasi mark on the silkscreen -----------------------------------------
# A 14 mm washer: 1.4 mm ring band with the boat monogram inside it, both in
# white silkscreen on bare board. The seal's outer ring text is omitted
# deliberately: at this diameter it falls under 1 mm, below the silkscreen
# minimum, and would print as a smudge. Strokes are 0.2 mm on a
# 0.12 mm pitch so adjacent rows overlap into solid fill.
import json as _json
_lg = _json.load(open(os.path.join(HERE, 'logo_segs.json')))
LOGO_X, LOGO_Y = 81.5, 51.5
for _x0, _y0, _x1, _y1 in _lg['segs']:
    edge.append(f'\t(gr_line (start {BX+LOGO_X+_x0:.3f} {BY+LOGO_Y+_y0:.3f})'
                f' (end {BX+LOGO_X+_x1:.3f} {BY+LOGO_Y+_y1:.3f})'
                f' (stroke (width 0.2) (type solid)) (layer "F.SilkS") (uuid {U()}))')

def rect(x0, y0, x1, y1, w=0.12):
    edge.append(f'\t(gr_rect (start {BX+x0:.2f} {BY+y0:.2f}) (end {BX+x1:.2f} {BY+y1:.2f})'
                f' (stroke (width {w}) (type default)) (fill none) (layer "F.SilkS") (uuid {U()}))')

# devkit outline, drawn 0.9 mm outside the real body so it never crosses the
# socket footprints' own silkscreen
rect(A1_BODY[0] - 0.9, A1_BODY[1] - 0.9, A1_BODY[2] + 0.9, A1_BODY[3] + 0.9)
# Ethernet module outline, 0.5 mm outside the true body for the same reason,
# with the RJ45 face sketched on the edge it protrudes from
_g = 0.5
rect(W5500_BODY[0] - _g, W5500_BODY[1] - _g, W5500_BODY[2] + _g, W5500_BODY[3] + _g)
_mx = (W5500_BODY[0] + W5500_BODY[2]) / 2
_jy0, _jy1 = W5500_BODY[1] - RJ45_OUT, W5500_BODY[1] - _g - 0.3
for (x0, y0, x1, y1) in ((_mx - RJ45_W/2, _jy0, _mx + RJ45_W/2, _jy0),
                         (_mx - RJ45_W/2, _jy0, _mx - RJ45_W/2, _jy1),
                         (_mx + RJ45_W/2, _jy0, _mx + RJ45_W/2, _jy1)):
    edge.append(f'\t(gr_line (start {BX+x0:.2f} {BY+y0:.2f}) (end {BX+x1:.2f} {BY+y1:.2f})'
                f' (stroke (width 0.12) (type default)) (layer "F.SilkS") (uuid {U()}))')

texts = [(8.5, 4.4, 'RJ45 THIS EDGE', 1.0),
         (4.0, 31.3, 'W5500 MODULE  PIN 1 AT TOP', 0.9),   # inside its outline
         (1.2, 35.3, '5V IN  SQ PAD = +', 1.0),          # above J13
         (12.0, 39.3, '+', 1.0), (12.0, 44.4, '-', 1.0),  # beside J13's pins
         (16.0, 90.0, 'SYNC IN 3V3', 1.0),                # beside J14
         (16.0, 93.0, 'J1-J12: SQ PAD = DATA', 0.9),
         (37.5, 73.5, 'ESP32-S3-DEVKITC-1', 0.9),         # inside the devkit outline,
         (37.5, 76.0, 'USB PORTS THIS END', 0.9),         # below the last socket pin
         # revB, and it MUST say so. revA is 22.86 mm between the socket
         # rows and revB is 25.4 - two boards that look identical, take
         # different devkits, and cannot be told apart on a shelf without a
         # caliper.
         #
         # Split over two lines and shrunk: the single 1.2 mm line ran into
         # SW1 at x 22.9, and moving it down to y 62 to dodge that put it
         # through C1 (y 61.6-71.7) and C2 instead - 3 overlaps became 92.
         # Free space here is narrow; check the placement box dump before
         # moving any silkscreen text.
         (3.0, 73.5, 'BAYBASI COLUMN CTRL', 0.9),
         (3.0, 76.8, 'revB', 1.2),
         # Switch legend. Weights sit left of their own pole (SW1 pads 1-4 at
         # y 69.00/71.54/74.08/76.62, body starts at x 22.9). The sum goes
         # below, kept short so it stops before R7 at x 27.5.
         (20.8, 69.4, '1', 0.85), (20.8, 71.94, '2', 0.85),
         (20.8, 74.48, 'SP', 0.85), (20.8, 77.02, 'SP', 0.85),
         # Measured, not estimated: at size 0.8 this font runs ~0.74 mm per
         # character, so the earlier 17-char version was 12.6 mm wide and
         # reached R7's pads at x 28.3. 12 characters from x 16 ends at 24.9,
         # clear of R7 by 2.6 mm.
         (16.0, 82.5, 'COL=2+1 ON=1', 0.8)]
# The per-connector refdes J1..J12 already print the panel number next to each
# terminal, so no "PANELS 1-6 / 7-12" banners.
for tx, ty, s_, sz in texts:
    edge.append(f'\t(gr_text "{s_}" (at {BX+tx:.3f} {BY+ty:.3f}) (layer "F.SilkS") (uuid {U()})'
                f' (effects (font (size {sz} {sz}) (thickness {0.2 if sz >= 1.2 else 0.15})) (justify left)))')

nets = '\n'.join(f'\t(net {i} "{n}")' for i, n in enumerate(NETLIST))
with open(OUT, 'w') as f:
    f.write(f'''(kicad_pcb (version 20241229) (generator "baybasi-gen") (generator_version "10.0")
\t(general (thickness 1.6) (legacy_teardrops no))
\t(paper "A3")
\t(layers
\t\t(0 "F.Cu" signal) (2 "B.Cu" signal)
\t\t(9 "F.Adhes" user "F.Adhesive") (11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user) (15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen") (7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user) (3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings") (19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1") (23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user) (27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard") (29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user) (33 "B.Fab" user)
\t)
\t(setup
\t\t(pad_to_mask_clearance 0)
\t\t(allow_soldermask_bridges_in_footprints no)
\t)
{nets}
{chr(10).join(body)}
{chr(10).join(edge)}
{zone}
)
''')
print(f'wrote {OUT}')
print(f'  {len(FP)} footprints, {len(NETLIST)-1} nets, board {BW:.0f} x {BH:.0f} mm')
print(f'  W5500 header row spacing {W5500_ROW_MM} mm (WIZ820io UM V1.0 sec.5, symbol B)')
