#!/usr/bin/env python3
"""Render the illustrated views of the unit enclosure and label them.

Each illustration scene in enclosure.scad echoes the 3D points its labels
point at ("ANCHOR|name|x|y|z"). This script renders the scene with a fixed
camera, projects those points into the image with the same camera maths
OpenSCAD uses, and draws the callouts. Run from this directory:

    python3 annotate_enclosure.py            # writes enclosure/illus-*.png
    python3 annotate_enclosure.py --debug    # marks the raw anchors instead

Needs openscad on PATH and Pillow.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCAD = "enclosure.scad"
OUT = "enclosure"
FOV = 22.5                      # OpenSCAD's default vertical field of view
INK = (29, 39, 51)
PAPER = (255, 255, 255)
BG = (248, 248, 248)

FONT = "/System/Library/Fonts/SFNS.ttf"
FONT_FALLBACK = "/System/Library/Fonts/Helvetica.ttc"


def font(size, bold=False):
    for path in (FONT, FONT_FALLBACK):
        try:
            f = ImageFont.truetype(path, size)
            if bold:
                try:
                    f.set_variation_by_name("Semibold")
                except Exception:
                    pass
            return f
        except OSError:
            continue
    return ImageFont.load_default()


def project(p, eye, center, w, h):
    eye, center, p = (np.asarray(v, float) for v in (eye, center, p))
    f = center - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, (0, 0, 1))
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    d = p - eye
    t = np.tan(np.radians(FOV) / 2)
    x, y, z = d @ s, d @ u, d @ f
    return ((x / (z * t * w / h) + 1) / 2 * w, (1 - y / (z * t)) / 2 * h)


def render(view, tmp):
    png = os.path.join(tmp, view["name"] + ".png")
    w, h = view["size"]
    cmd = ["openscad"] + (["--render"] if view.get("render") else [])
    for k, v in view.get("defs", {}).items():
        cmd += ["-D", f"{k}={v}"]
    cmd += ["-D", f'part="{view["part"]}"', "-o", png,
            f"--imgsize={w},{h}", "--projection=p", "--colorscheme=Tomorrow",
            "--camera=%g,%g,%g,%g,%g,%g" % (*view["eye"], *view["center"]), SCAD]
    # the scene's echo() lines arrive on stderr; they carry the anchors
    log = subprocess.run(cmd, check=True, capture_output=True, text=True).stderr
    for line in log.splitlines():
        if "WARNING" in line or "ERROR" in line:
            print(view["name"], line, file=sys.stderr)
    anchors = {}
    for line in log.splitlines():
        if "ANCHOR|" in line:
            _, name, x, y, z = line.split('"')[1].split("|")
            anchors[name] = project((float(x), float(y), float(z)), view["eye"], view["center"], w, h)
    return Image.open(png).convert("RGB"), anchors


def text_block(draw, lines, size):
    f1, f2 = font(size, True), font(int(size * 0.8))
    rows = [(lines[0], f1)] + [(t, f2) for t in lines[1:]]
    widths = [draw.textbbox((0, 0), t, font=f)[2] for t, f in rows]
    heights = [int(f.size * 1.28) for _, f in rows]
    return rows, max(widths), sum(heights), heights


def callout(img, anchor, lines, offset, size=26):
    draw = ImageDraw.Draw(img)
    ax, ay = anchor
    rows, tw, th, heights = text_block(draw, lines, size)
    pad = int(size * 0.45)
    lx, ly = ax + offset[0], ay + offset[1]
    align = offset[2] if len(offset) > 2 else ("start" if offset[0] >= 0 else "end")
    bx0 = lx if align == "start" else lx - tw - 2 * pad
    by0 = ly - th / 2 - pad
    box = (bx0, by0, bx0 + tw + 2 * pad, by0 + th + 2 * pad)
    # leader to the nearest point on the box
    tx = min(max(ax, box[0]), box[2])
    ty = min(max(ay, box[1]), box[3])
    draw.line((ax, ay, tx, ty), fill=PAPER, width=7)
    draw.line((ax, ay, tx, ty), fill=INK, width=3)
    r = 7
    draw.ellipse((ax - r - 2, ay - r - 2, ax + r + 2, ay + r + 2), fill=PAPER)
    draw.ellipse((ax - r, ay - r, ax + r, ay + r), fill=INK)
    draw.rounded_rectangle(box, radius=int(size * 0.35), fill=PAPER, outline=INK, width=3)
    y = by0 + pad
    for (t, f), hh in zip(rows, heights):
        draw.text((bx0 + pad, y), t, font=f, fill=INK)
        y += hh


def title(img, lines, size=40):
    draw = ImageDraw.Draw(img)
    f1, f2 = font(size, True), font(int(size * 0.62))
    draw.text((40, 30), lines[0], font=f1, fill=INK)
    y = 30 + int(size * 1.3)
    for t in lines[1:]:
        draw.text((40, y), t, font=f2, fill=INK)
        y += int(size * 0.62 * 1.35)


def debug(img, anchors):
    draw = ImageDraw.Draw(img)
    for name, (x, y) in anchors.items():
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(220, 30, 30))
        draw.text((x + 9, y - 9), name, font=font(20, True), fill=(220, 30, 30))


# Cameras: the unit views stand the box up on its door (Z up), seen from the
# front and to the right; the cutaways look square-on at a thin slice.
UNIT_CENTER = (62, -25, 145)
UNIT_EYE = (780, -1146, 496)

VIEWS = [
    dict(name="closed", part="illus_closed", render=True, size=(1500, 1900), eye=UNIT_EYE, center=UNIT_CENTER),
    dict(name="open", part="illus_open", size=(1500, 1900), eye=UNIT_EYE, center=UNIT_CENTER),
    dict(name="lead1", part="illus_lead", defs={"step": 1}, render=True, size=(1000, 1000),
         eye=(6, -21.4, 36), center=(6, 49, 36)),
    dict(name="lead2", part="illus_lead", defs={"step": 2}, render=True, size=(1000, 1000),
         eye=(6, -21.4, 36), center=(6, 49, 36)),
    dict(name="lead3", part="illus_lead", defs={"step": 3}, render=True, size=(1000, 1000),
         eye=(6, -21.4, 36), center=(6, 49, 36)),
    dict(name="mount_front", part="illus_mount", defs={"view": '"front"'}, size=(1500, 1900),
         eye=UNIT_EYE, center=UNIT_CENTER),
    dict(name="mount_back", part="illus_mount", defs={"view": '"back"'}, size=(1100, 1500),
         eye=(69.5, 1000, 161), center=(69.5, 0, 161)),
    dict(name="mount_bolt", part="illus_mount", defs={"view": '"bolt"'}, render=True, size=(900, 900),
         eye=(104, -2, 2), center=(104, 154.35, 2)),
    dict(name="mount_screw", part="illus_mount", defs={"view": '"screw"'}, render=True, size=(900, 900),
         eye=(125, 9, -6), center=(125, 135, -6)),
]


# Callouts: anchor name -> (lines, (dx, dy)). The box sits dx, dy from its
# anchor: to the right of that point if dx > 0, to the left if dx < 0.
LABELS = {
    "closed": {
        "feed_minus": (["- feed, in from below:", "up the left side, over into the roof"], (-215, -40)),
        "drops":      (["Rows 1-6 power", "6 pairs up"], (75, -40)),
        "drops_dn":   (["Rows 7-12 power", "6 pairs down"], (-60, 60)),
        "lid":        (["Fuse lid", "6 screws; off to change a fuse"], (290, -80)),
        "led":        (["LED window", "shows a blown fuse"], (-230, 40)),
        "door":       (["Door, inside face"], (25, 150)),
        "dip":        (["Column DIP switch window"], (-190, -95)),
        "eth":        (["Network cable (Cat5e)", "tied to the lug below the jack"], (105, -150)),
        "leads":      (["Rows 1-6 data: 6 leads", "clamped in the right wall"], (100, -10)),
        "cover":      (["Controller cover", "4 screws; clamps the data leads"], (285, 130)),
        "feed_plus":  (["+ feed, in from below"], (-45, 170)),
    },
    "open": {
        "feed_minus": (["- feed in"], (-215, -30)),
        "drops":      (["Rows 1-6 drops out of the roof"], (75, -40)),
        "drops_dn":   (["Rows 7-12 drops out of the floor"], (-60, 60)),
        "clamp_top":  (["Feed clamp", "printed, 2 screws"], (315, -40)),
        "lug_minus":  (["- lug on the - stud"], (-330, -10)),
        "block":      (["Fuse block", "clear cover on"], (270, -110)),
        "channel":    (["Rows 1-6 drops run up", "the right channel"], (180, 40)),
        "fuses":      (["12 x 20 A fuses"], (290, 60)),
        "lug_plus":   (["+ lug on the + stud"], (335, 0)),
        "tap":        (["R07 + CTRL: this fuse", "also feeds the board (J13)"], (-165, -10)),
        "dip":        (["Column DIP switch"], (-205, -70)),
        "usb":        (["Devkit USB ports", "(cover off to reach)"], (-150, 30)),
        "ethmod":     (["Ethernet module"], (305, -60)),
        "jaws":       (["Lead jaws: the cover", "clamps all six leads"], (180, 25)),
        "board":      (["Controller board", "on 29.5 mm posts"], (285, 60)),
        "clamp_bot":  (["Feed clamp"], (315, 130)),
        "feed_plus":  (["+ feed in", "runs up under the board"], (-45, 170)),
    },
    "lead1": {
        "lead_in":    (["Lead in its groove"], (-40, -150)),
        "tub_ribs":   (["Tub's ribs"], (90, 200)),
        "to_j10":     (["Green and white", "on to J10"], (-20, -170)),
        "outside":    (["To the", "panel"], (-20, 170, "start")),
    },
    "lead2": {
        "cover_ribs": (["Cover's ribs sit", "between the tub's"], (80, -60)),
        "gusset":     (["45° gussets:", "no supports"], (150, 120)),
    },
    "lead3": {
        "lead_in":    (["Pressed into a wave", "by all four ribs"], (210, 240)),
        "mouth":      (["Chamfered", "mouth"], (-30, 150)),
    },
    "mount_front": {
        "screw_top":  (["8 screws hold the box to the door", "#8 pan-head wood screws (M4 + nut on metal)"], (-40, -110)),
        "bolt":       (["4 block bolts, threads up", "heads trapped behind the floor"], (235, -50)),
        "seat":       (["The fuse block drops over", "the bolts: washer + nut each"], (240, 0)),
        "screw_pcb":  (["2 screws sit under the board:", "fit them before the board"], (225, 10)),
        "screw_bot":  (["2 beside the bottom clamp"], (215, 60)),
        "door":       (["Door, inside face"], (30, 40)),
    },
    "mount_back": {
        "bolt_head":  (["Block bolt heads", "in hex pockets: they can't", "turn, and the door holds them in"], (130, -60)),
        "door_hole":  (["8 holes for the", "door screws"], (-170, 60)),
        "back":       (["Flat back sits on the door"], (-225, 620, "start")),
    },
    "mount_bolt": {
        "nut":        (["Washer + nut"], (120, 0)),
        "block":      (["Fuse block base"], (-208, -145, "start")),
        "floor":      (["Tub floor, 6 mm under the block"], (-247, 190, "start")),
        "head":       (["Bolt head, captive"], (240, 60)),
        "door":       (["Door"], (76, 107)),
    },
    "mount_screw": {
        "head":       (["Pan-head screw + washer"], (-60, -130)),
        "floor":      (["Tub floor, 3 mm"], (-30, -80)),
        "thread":     (["Screw into the door"], (100, 110)),
        "door":       (["Door"], (-60, 90)),
    },
}

TITLES = {
    "closed":      ["The unit, closed", "On its door, as you see it with the door open"],
    "open":        ["The unit with both covers off", "What goes where"],
    "lead":        ["How a data lead is clamped",
                    "A slice through J10's lead, seen end on"],
    "mount_front": ["How the box mounts to the door", "The empty tub, screwed on, ready for the fuse block"],
    "mount_back":  ["The back of the tub", "Door removed"],
    "mount_cut":   ["Fasteners, cut in half", "Left: a fuse-block bolt.  Right: a door screw."],
}

STEPS = ["1  Lay the lead in its groove, into J10",
         "2  Screw the cover on over it",
         "3  Clamped: a tug stops at the ribs"]


def header(img, lines, band=150):
    out = Image.new("RGB", (img.width, img.height + band), BG)
    out.paste(img, (0, band))
    title(out, lines)
    return out


def labelled(v, img, anchors):
    for name, (lines, off) in LABELS.get(v["name"], {}).items():
        if name in anchors:
            callout(img, anchors[name], lines, off, size=v.get("font", 26))
    return img


def side_by_side(imgs, gap=30, heads=None, head_h=70, size=30):
    h = max(i.height for i in imgs)
    w = sum(i.width for i in imgs) + gap * (len(imgs) - 1)
    out = Image.new("RGB", (w, h + (head_h if heads else 0)), BG)
    draw = ImageDraw.Draw(out)
    x = 0
    for k, im in enumerate(imgs):
        if heads:
            draw.text((x + 20, 15), heads[k], font=font(size, True), fill=INK)
        out.paste(im, (x, head_h if heads else 0))
        x += im.width + gap
    return out


def main():
    global OUT
    dbg = "--debug" in sys.argv
    if "--out" in sys.argv:
        OUT = sys.argv[sys.argv.index("--out") + 1]
    os.makedirs(OUT, exist_ok=True)
    done = {}
    with tempfile.TemporaryDirectory() as tmp:
        for v in VIEWS:
            img, anchors = render(v, tmp)
            if dbg:
                debug(img, anchors)
                img.save(os.path.join(OUT, f"debug-{v['name']}.png"))
                print(v["name"], {k: (round(x), round(y)) for k, (x, y) in anchors.items()})
                continue
            done[v["name"]] = labelled(v, img, anchors)
    if dbg:
        return
    save = lambda im, name: (im.save(os.path.join(OUT, name), optimize=True), print("  ", name))
    for n in ("closed", "open", "mount_front", "mount_back"):
        save(header(done[n], TITLES[n]), f"illus-{n.replace('_', '-')}.png")
    steps = [done[f"lead{k}"].crop((0, 0, 1000, 960)) for k in (1, 2, 3)]
    save(header(side_by_side(steps, heads=STEPS), TITLES["lead"]), "illus-lead.png")
    cuts = [done["mount_bolt"], done["mount_screw"]]
    save(header(side_by_side(cuts), TITLES["mount_cut"]), "illus-mount-cut.png")


if __name__ == "__main__":
    main()
