#!/usr/bin/env python3
"""Generate the Baybasi pixel-wall controller schematic for KiCad 10.

Connectivity is carried by net labels placed exactly on pin endpoints, which is
what keeps this generator small and robust: no wire routing, no stub-direction
logic, and the netlist comes out identical to a hand-wired sheet.
"""
import re, uuid, os

STOCK = '/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols'
ESPR  = os.path.expanduser(
    '~/Documents/KiCad/10.0/3rdparty/symbols/com_github_espressif_kicad-libraries')
OUT   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'baybasi-ctrl.kicad_sch')

_cache = {}
def lib_text(lib):
    if lib not in _cache:
        p = (f'{ESPR}/Espressif.kicad_sym' if lib == 'PCM_Espressif'
             else f'{STOCK}/{lib}.kicad_sym')
        _cache[lib] = open(p).read()
    return _cache[lib]

def raw_block(lib, name):
    t = lib_text(lib)
    i = t.index(f'\n\t(symbol "{name}"')
    j = t.find('\n\t(symbol "', i + 5)
    return t[i + 1: j if j > 0 else len(t)]

def resolve(lib, name):
    """Return (block_text, pins). Follows (extends ...) the way KiCad does."""
    blk = raw_block(lib, name)
    m = re.search(r'\(extends "([^"]+)"', blk)
    if m:
        base = m.group(1)
        bblk = raw_block(lib, base)
        # graft the base's unit sub-blocks onto the derived symbol, renamed
        units = re.findall(r'\n\t\t\(symbol "' + re.escape(base) + r'_[^"]*".*?(?=\n\t\t\(symbol "|\n\t\)\s*$)',
                           bblk, re.S)
        if not units:
            k = bblk.index(f'\t\t(symbol "{base}_')
            units = [bblk[k:bblk.rindex('\n\t)')]]
        graft = ''.join(u.replace(f'"{base}_', f'"{name}_') for u in units)
        blk = re.sub(r'\n\t\t\(extends "[^"]+"\)', '', blk)   # KiCad caches resolved, not derived
        blk = blk.rstrip()
        assert blk.endswith(')')
        blk = blk[:blk.rindex('\n\t)')] + '\n' + graft + '\n\t)\n'
    pins = {}
    for pm in re.finditer(r'\(pin\s+(\w+)\s+\w+\s*\n?\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)(.*?)\(number "([^"]*)"',
                          blk, re.S):
        pins[pm.group(6)] = (float(pm.group(2)), float(pm.group(3)), pm.group(1))
    return blk, pins

U = lambda: str(uuid.uuid4())
SH = U()

# ---------------------------------------------------------------- design ----
# ref: (lib, symbol, value, footprint-hint, x, y, {pin: net})
C = []
def part(ref, lib, sym, val, fp, x, y, nets, nc=()):
    C.append(dict(ref=ref, lib=lib, sym=sym, val=val, fp=fp, x=x, y=y, nets=nets, nc=list(nc)))

# --- MCU -------------------------------------------------------------------
A1 = {21: '+5V', 22: 'GND', 23: 'GND', 24: 'GND', 44: 'GND',
      16: 'ETH_CS', 17: 'ETH_MOSI', 18: 'ETH_SCK', 19: 'ETH_MISO', 20: 'ETH_INT',
      4: 'D1_3V3', 5: 'D2_3V3', 6: 'D3_3V3', 7: 'SYNC_IN', 8: 'ETH_RST', 12: 'OE_N',
      41: 'D4_3V3', 40: 'D5_3V3', 27: 'D6_3V3', 35: 'D7_3V3', 36: 'D8_3V3',
      37: 'D9_3V3', 38: 'D10_3V3', 39: 'D11_3V3', 28: 'D12_3V3',
      # Column select, batch 2. Devkit pads, not GPIO numbers:
      #   pad 15 = GPIO 9, pad 9 = GPIO 16, pad 10 = GPIO 17, pad 11 = GPIO 18.
      # All four were previously in A1L_NC. See hw/DIP-COLUMN-SELECT.md; the
      # pad-to-GPIO reading is cross-checked against FABRICATION.md's pin map,
      # which agrees on every pad the two have in common.
      15: 'COL_B0', 9: 'COL_B1', 10: 'COL_SP0', 11: 'COL_SP1'}
# The devkit sits on two 1x22 sockets, not one 44-pin part: JLCPCB places one
# component per designator, and no 2x22 socket exists at 0.900 in spacing.
# Left row is devkit pads 1..22 top-to-bottom; right row is 44..23.
A1L_NETS = {i: A1[i] for i in range(1, 23) if i in A1}
A1R_NETS = {i: A1[45 - i] for i in range(1, 23) if (45 - i) in A1}
A1L_NC = [str(i) for i in range(1, 23) if i not in A1L_NETS]
A1R_NC = [str(i) for i in range(1, 23) if i not in A1R_NETS]
HDR22 = 'Connector_PinHeader_2.54mm:PinHeader_1x22_P2.54mm_Vertical'
part('A1L', 'Connector_Generic', 'Conn_01x22', 'ESP32-S3 socket L', HDR22,
     76.2, 152.4, {str(k): v for k, v in A1L_NETS.items()}, A1L_NC)
part('A1R', 'Connector_Generic', 'Conn_01x22', 'ESP32-S3 socket R', HDR22,
     114.3, 152.4, {str(k): v for k, v in A1R_NETS.items()}, A1R_NC)

# --- column select ---------------------------------------------------------
# Four poles to GND, read with internal pull-ups, so closed = 0 on the pin and
# the firmware inverts. Poles 1-2 are the column; 3-4 are spares, placed and
# routed now because the part has them and traces are free.
#
#   pole 1: pad 1 <-> 8    COL_B0  (GPIO 9)
#   pole 2: pad 2 <-> 7    COL_B1  (GPIO 16)
#   pole 3: pad 3 <-> 6    COL_SP0 (GPIO 17)
#   pole 4: pad 4 <-> 5    COL_SP1 (GPIO 18)
part('SW1', 'Switch', 'SW_DIP_x04', 'DSWB04LHGET',
     'Button_Switch_THT:SW_DIP_SPSTx04_Slide_9.78x12.34mm_W7.62mm_P2.54mm',
     60.96, 200.0,
     {'1': 'COL_B0', '2': 'COL_B1', '3': 'COL_SP0', '4': 'COL_SP1',
      '5': 'GND', '6': 'GND', '7': 'GND', '8': 'GND'})

# --- Ethernet module: WIZ850io, two 1x6 rows -------------------------------
part('M1', 'Connector_Generic', 'Conn_01x06', 'WIZ850io J1',
     'Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical', 172.72, 76.2,
     {'1': 'GND', '2': 'GND', '3': 'ETH_MOSI', '4': 'ETH_SCK', '5': 'ETH_CS', '6': 'ETH_INT'})
part('M2', 'Connector_Generic', 'Conn_01x06', 'WIZ850io J2',
     'Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical', 172.72, 111.76,
     {'1': 'GND', '2': '+3V3E', '3': '+3V3E', '5': 'ETH_RST', '6': 'ETH_MISO'}, ['4'])

# --- level shifters --------------------------------------------------------
for ref, base, x in (('U1', 0, offs) for ref, offs in ()):
    pass
for idx, (ref, first, x) in enumerate((('U1', 1, 226.06), ('U2', 7, 297.18))):
    # pin 19 is /OE. Pulled up so the shifters come out of reset DISABLED;
    # firmware drives GPIO8 low once the outputs are safe to enable.
    nets = {'20': '+5V', '10': 'GND', '1': '+5V', '19': 'OE_N', '8': 'GND', '9': 'GND'}
    for k in range(6):                      # A1..A6 = pins 2..7 ; B1..B6 = pins 18..13
        nets[str(2 + k)]  = f'D{first+k}_3V3'
        nets[str(18 - k)] = f'D{first+k}_5V'
    part(ref, '74xx', '74HC245', 'SN74AHCT245N',
         'Package_DIP:DIP-20_W7.62mm', x, 152.4, nets, ['12', '11'])

# --- series resistors and output connectors --------------------------------
for n in range(1, 13):
    col, row = (n - 1) // 6, (n - 1) % 6
    x = 358.14 + col * 50.8
    y = 88.9 + row * 20.32
    part(f'R{n}', 'Device', 'R', '330',
         'Resistor_SMD:R_0805_2012Metric',
         x, y, {'1': f'D{n}_5V', '2': f'OUT{n}'})
    part(f'J{n}', 'Connector_Generic', 'Conn_01x02', f'PANEL {n}',
         'TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-2-3.5-H_1x02_P3.50mm_Horizontal',
         x + 25.4, y, {'1': f'OUT{n}', '2': 'GND'})
    # While /OE is high (boot, reset, no devkit) the 245 outputs float and a
    # floating WS2812B DIN picks up noise as random pixels. 10k to GND parks
    # every output at a clean LOW instead; it costs 0.5 mA per line when driven.
    part(f'R{15+n}', 'Device', 'R', '10k',
         'Resistor_SMD:R_0805_2012Metric',
         x + 12.7, y + 8.89, {'1': f'OUT{n}', '2': 'GND'})

# --- power ------------------------------------------------------------------
part('J13', 'Connector', 'Screw_Terminal_01x02', '5V IN',
     'TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal', 25.4, 62.23,
     {'1': 'VIN_RAW', '2': 'GND'})
part('Q1', 'Transistor_FET', 'AO3401A', 'AO3401A',
     'Package_TO_SOT_SMD:SOT-23', 60.96, 55.88,
     # AO3401A is 1=G 2=S 3=D. Reverse-polarity P-FET: DRAIN faces the input,
     # SOURCE feeds the load, gate to GND. Correct polarity: the body diode
     # (anode = drain) conducts input->load until Vgs = -5 V turns the channel
     # on. Reversed: the diode is reverse-biased and Vgs >= 0 keeps it off.
     # (QA 2026-09-07: S and D were transposed - the diode would have conducted
     # straight through the load on a reversed supply.)
     {'1': 'VGATE', '2': 'V5_PROT', '3': 'VIN_RAW'})
# 10k, not 100k: JLCPCB's basic 100k line was short at order time and a gate
# pull-down works the same at either value (0.5 mA, 2.5 mW at 5 V).
part('R13', 'Device', 'R', '10k',
     'Resistor_SMD:R_0805_2012Metric',
     45.72, 71.12, {'1': 'VGATE', '2': 'GND'})
part('L1', 'Device', 'L', '10uH 2A',
     'Inductor_SMD:L_Bourns_SRN6045TA', 88.9, 55.88,
     {'1': 'V5_PROT', '2': '+5V'})
part('C1', 'Device', 'C', '470uF 16V',
     'Capacitor_THT:CP_Radial_D10.0mm_P3.50mm', 111.76, 66.04, {'1': '+5V', '2': 'GND'})
part('U3', 'Regulator_Linear', 'AMS1117-3.3', 'AMS1117-3.3',
     'Package_TO_SOT_SMD:SOT-223-3_TabPin2', 149.86, 55.88,
     {'3': '+5V', '2': '+3V3E', '1': 'GND'})
part('C3', 'Device', 'C', '10uF',
     'Capacitor_THT:CP_Radial_D5.0mm_P2.50mm', 132.08, 66.04, {'1': '+5V', '2': 'GND'})
part('C4', 'Device', 'C', '22uF',
     'Capacitor_THT:CP_Radial_D5.0mm_P2.50mm', 170.18, 66.04, {'1': '+3V3E', '2': 'GND'})
part('C2', 'Device', 'C', '100uF',
     'Capacitor_THT:CP_Radial_D6.3mm_P2.50mm', 195.58, 66.04, {'1': '+3V3E', '2': 'GND'})
# /OE pull-up goes to the board's own 3V3E rail: 5 V here would back-drive
# GPIO8 (not 5 V tolerant) through 10k whenever the devkit is unpowered, and
# 3.3 V clears the AHCT VIH of 2.0 V with margin. 3V3E rather than the devkit's
# 3V3 so the outputs stay disabled even with no devkit plugged in.
part('R15', 'Device', 'R', '10k',
     'Resistor_SMD:R_0805_2012Metric', 226.06, 111.76, {'1': 'OE_N', '2': '+3V3E'})
part('R14', 'Device', 'R', '10k',
     'Resistor_SMD:R_0805_2012Metric',
     205.74, 111.76, {'1': 'ETH_RST', '2': '+3V3E'})
part('J14', 'Connector_Generic', 'Conn_01x02', 'SYNC IN (opt)',
     'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
     45.72, 180.34, {'1': 'SYNC_IN', '2': 'GND'})
for i, (ref, net, x) in enumerate([('C5', '+5V', 236.22), ('C6', '+5V', 307.34),
                                   ('C7', '+3V3E', 220.98), ('C8', '+5V', 132.08),
                                   ('C9', '+5V', 45.72)]):
    part(ref, 'Device', 'C', '100nF',
         'Capacitor_SMD:C_0805_2012Metric', x, 91.44 if i < 3 else 220.98,
         {'1': net, '2': 'GND'})

# power flags so ERC knows the rails are driven from a connector
for i, (net, x) in enumerate((('+5V', 25.4), ('GND', 86.36))):
    part(f'#FLG{i}', 'power', 'PWR_FLAG', 'PWR_FLAG', '', x, 30.48, {'1': net})

# ------------------------------------------------------------------ emit ----
used = sorted({(c['lib'], c['sym']) for c in C})
libsyms, pinmaps = [], {}
for lib, sym in used:
    blk, pins = resolve(lib, sym)
    pinmaps[(lib, sym)] = pins
    blk = re.sub(r'^\t\(symbol "' + re.escape(sym) + r'"',
                 f'\t(symbol "{lib}:{sym}"', blk, count=1)
    libsyms.append(blk.rstrip())

body = []
for c in C:
    pins = pinmaps[(c['lib'], c['sym'])]
    su = U()
    props = [
        f'\t\t(property "Reference" "{c["ref"]}" (at {c["x"]:.2f} {c["y"]-2.54:.2f} 0) (effects (font (size 1.27 1.27)) (justify left)))',
        f'\t\t(property "Value" "{c["val"]}" (at {c["x"]:.2f} {c["y"]+2.54:.2f} 0) (effects (font (size 1.27 1.27)) (justify left)))',
        f'\t\t(property "Footprint" "{c["fp"]}" (at {c["x"]:.2f} {c["y"]:.2f} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
    ]
    pin_uuids = '\n'.join(f'\t\t(pin "{p}" (uuid {U()}))' for p in pins)
    hidden = ' (attr (exclude_from_bom) (dnp no))' if c['ref'].startswith('#') else ''
    body.append(
f'''\t(symbol (lib_id "{c['lib']}:{c['sym']}") (at {c['x']:.2f} {c['y']:.2f} 0) (unit 1)
\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
\t\t(uuid {su})
{chr(10).join(props)}
{pin_uuids}
\t\t(instances (project "baybasi-ctrl" (path "/{SH}" (reference "{c['ref']}") (unit 1))))
\t)''')
    for pnum, net in c['nets'].items():
        px, py, _ = pins[pnum]
        ax, ay = c['x'] + px, c['y'] - py
        body.append(f'\t(label "{net}" (at {ax:.2f} {ay:.2f} 0) '
                    f'(effects (font (size 1.27 1.27)) (justify left bottom)) (uuid {U()}))')
    for pnum in c['nc']:
        px, py, _ = pins[pnum]
        body.append(f'\t(no_connect (at {c["x"]+px:.2f} {c["y"]-py:.2f}) (uuid {U()}))')

TEXT = [(25.4, 22.86, "BAYBASI PIXEL WALL - COLUMN CONTROLLER   rev A"),
        (25.4, 40.64, "POWER: reverse-protected, LC-filtered 5 V from this column's LED supply"),
        (152.4, 40.64, "3V3E: dedicated rail, W5500 only"),
        (226.06, 132.08, "LEVEL SHIFT 3V3 -> 5V   (AHCT: TTL thresholds)"),
        (358.14, 76.2, "12 x SERIES-TERMINATED OUTPUT   DATA + GND, no +5 V pin"),
        (88.9, 210.82, "Connectivity is by net label; labels sit on pin endpoints."),
        (226.06, 213.36, "U1/U2 pins 8,9 (A6,A7) tied low: unused AHCT inputs must not float."),
        (226.06, 215.9, "/OE (pin 19) pulled to 3V3E via R15: outputs Hi-Z until GPIO8 drives it low."),
        (358.14, 213.36, "R16-R27: 10k to GND on every OUT - DIN sits LOW while the 245s are disabled."),
        (25.4, 43.18, "Q1 AO3401A: drain = input side, source = load side, gate to GND via R13."),
        (152.4, 43.18, "W5500 RSTn: R14 10k to 3V3E and GPIO15 (devkit pad 8) for a firmware reset.")]
for x, y, t in TEXT:
    body.append(f'\t(text "{t}" (at {x:.2f} {y:.2f} 0) '
                f'(effects (font (size 1.6 1.6)) (justify left)) (uuid {U()}))')

with open(OUT, 'w') as f:
    f.write(f'''(kicad_sch (version 20250114) (generator "baybasi-gen") (generator_version "10.0")
\t(uuid {SH})
\t(paper "A2")
\t(lib_symbols
{chr(10).join(libsyms)}
\t)
{chr(10).join(body)}
)
''')
print(f'wrote {OUT}')
print(f'  {len(C)} components, {len(used)} distinct symbols, '
      f'{len({n for c in C for n in c["nets"].values()})} nets')
