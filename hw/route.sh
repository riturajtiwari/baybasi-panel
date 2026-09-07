#!/bin/bash
# Autoroute the board with Freerouting, headless, end to end.
#   ./route.sh [passes]      default 30
set -euo pipefail
PASSES=${1:-30}
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
KC=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
JAVA=/opt/homebrew/opt/openjdk@25/bin/java
FR="$(cd "$(dirname "$0")/../tools" && pwd)/freerouting.jar"
PCB=baybasi-ctrl.kicad_pcb

cp "$PCB" baybasi-ctrl.unrouted.bak
echo "== export DSN =="
$KPY - <<PY 2>&1 | grep -viE 'wxApp|memory leak' || true
import pcbnew
b = pcbnew.LoadBoard('$PCB')
gnd = b.GetNetcodeFromNetname('GND')
# Only GND copper survives a re-route: the stitching vias from gen_pcb.py and
# the pad ties added below. Everything else is Freerouting's to redo.
for t in list(b.GetTracks()):
    if t.Type() != pcbnew.PCB_VIA_T and t.GetNetCode() != gnd:
        b.Remove(t)
    elif t.Type() != pcbnew.PCB_VIA_T:
        b.Remove(t)            # old pad ties; re-made below so they stay idempotent

# Every surface-mount GND pad gets its own via and a short track to it. The
# pour alone is not enough: routing on the top layer boxes pads in and the
# fill cannot reach them (R23 pad 2 was the first casualty).
vias = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
pads = [p for f in b.GetFootprints() for p in f.Pads()]
edge = b.GetBoardEdgesBoundingBox()
def near_via(pt):
    return any((v.GetPosition() - pt).EuclideanNorm() < 100000 for v in vias)
def clear(pt, own):
    # 0.55 mm from every other pad's outline, 1.5 mm inside the board edge
    if not edge.Contains(pt): return False
    if (min(pt.x - edge.GetLeft(), edge.GetRight() - pt.x,
            pt.y - edge.GetTop(), edge.GetBottom() - pt.y) < 1500000): return False
    for p in pads:
        if p is own: continue
        bb = p.GetBoundingBox()
        dx = max(bb.GetLeft() - pt.x, 0, pt.x - bb.GetRight())
        dy = max(bb.GetTop() - pt.y, 0, pt.y - bb.GetBottom())
        if (dx*dx + dy*dy) ** 0.5 < 550000: return False
    return True
ties = 0
for p in pads:
    if p.GetNetCode() != gnd or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD: continue
    c = p.GetPosition()
    for dx, dy in ((0, 1900000), (0, -1900000), (1900000, 0), (-1900000, 0),
                   (0, 2400000), (0, -2400000), (2400000, 0), (-2400000, 0)):
        pt = pcbnew.VECTOR2I(c.x + dx, c.y + dy)
        if not clear(pt, p): continue
        if not near_via(pt):
            v = pcbnew.PCB_VIA(b); v.SetPosition(pt); v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetDrill(300000); v.SetWidth(600000); v.SetNetCode(gnd); b.Add(v); vias.append(v)
        t = pcbnew.PCB_TRACK(b); t.SetStart(c); t.SetEnd(pt); t.SetWidth(250000)
        t.SetLayer(pcbnew.F_Cu); t.SetNetCode(gnd); b.Add(t)
        ties += 1
        break
    else:
        print(f'  !! no via spot for GND pad {p.GetParentFootprint().GetReference()}.{p.GetNumber()}')
print(f'  {ties} SMD GND pads tied to vias')
for z in b.Zones(): z.UnFill()                 # a filled pour reads as an obstacle
assert pcbnew.ExportSpecctraDSN(b, 'baybasi-ctrl.dsn')
b.Save('$PCB')
PY

# Freerouting is stochastic: identical input gives different results run to run,
# and more passes can land on a worse board than fewer. Try a spread, keep the best.
echo "== route =="
BEST=999; BESTCFG=""
for CFG in "3 -" "3 -" "10 -" "$PASSES -" "10 prioritized" "$PASSES random" "60 sequential" "5 -"; do
  set -- $CFG; MP=$1; IS=$2
  ISARG=""; [ "$IS" != "-" ] && ISARG="-is $IS"
  printf "   %-3s passes %-12s ... " "$MP" "${IS/-/default}"
  OUT=$($JAVA -Djava.awt.headless=true -jar "$FR" \
        -de baybasi-ctrl.dsn -do try.ses -mp "$MP" -mt 4 $ISARG 2>&1 \
        | grep -viE 'IMKClient|IMKInput' || true)
  LINE=$(echo "$OUT" | grep -E 'Auto-routing stage completed' | tail -1)
  UNR=$(echo "$LINE" | sed -n 's/.*(\([0-9]*\) unrouted.*/\1/p'); UNR=${UNR:-999}
  VIO=$(echo "$LINE" | sed -n 's/.*and \([0-9]*\) violations.*/\1/p'); VIO=${VIO:-9}
  echo "$UNR unrouted, $VIO violations"
  if [ "$VIO" = "0" ] && [ "$UNR" -lt "$BEST" ]; then
    BEST=$UNR; BESTCFG="$MP/$IS"; cp try.ses baybasi-ctrl.ses
  fi
  [ "$BEST" = "0" ] && break
done
rm -f try.ses
echo "   best: $BEST unrouted (config $BESTCFG)"
[ "$BEST" = "0" ] || echo "   !! $BEST net(s) need routing by hand - see drc.rpt for which"

echo "== import + fill zones =="
$KPY - <<PY 2>&1 | grep -viE 'wxApp|memory leak'
import pcbnew
b = pcbnew.LoadBoard('$PCB')
assert pcbnew.ImportSpecctraSES(b, 'baybasi-ctrl.ses')
gnd = b.GetNetcodeFromNetname('GND')
MINW = int(0.25 * 1e6)                          # netclass Default width, nm
thin = [t for t in b.GetTracks()
        if t.Type() != pcbnew.PCB_VIA_T and t.GetWidth() < MINW]
for t in thin: t.SetWidth(MINW)
if thin: print(f'  widened {len(thin)} undersized track(s) to 0.25 mm')

# Freerouting leaves the odd via with copper on one layer only. They are
# electrically inert but DRC flags every one, so drop them. GND vias are
# skipped: they join the pours and carry no tracks by design.
segs = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
dropped = 0
for v in [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]:
    if v.GetNetCode() == gnd: continue
    p = v.GetPosition()
    layers = {s.GetLayer() for s in segs
              if (s.GetStart() - p).EuclideanNorm() < 1000 or (s.GetEnd() - p).EuclideanNorm() < 1000}
    if len(layers) < 2:
        b.Remove(v); dropped += 1
if dropped: print(f'  removed {dropped} single-layer via(s)')

# Fill, then hunt for pour islands that touch no via and no through-hole pad:
# those are cut off from the rest of the ground. Drop a via inside each one
# where the other layer's pour is also present, and fill again.
zone = [z for z in b.Zones() if z.GetNetCode() == gnd][0]
filler = pcbnew.ZONE_FILLER(b)
def anchors():
    pts = [t.GetPosition() for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() == gnd]
    pts += [p.GetPosition() for f in b.GetFootprints() for p in f.Pads()
            if p.GetNetCode() == gnd and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
    return pts
def inside(polys, pt, idx=-1, m=600000):
    return all(polys.Contains(pcbnew.VECTOR2I(pt.x + dx, pt.y + dy), idx)
               for dx, dy in ((0, 0), (m, 0), (-m, 0), (0, m), (0, -m)))
for rnd in range(6):
    filler.Fill(b.Zones())
    added = 0
    for L, O in ((pcbnew.F_Cu, pcbnew.B_Cu), (pcbnew.B_Cu, pcbnew.F_Cu)):
        mine, other = zone.GetFilledPolysList(L), zone.GetFilledPolysList(O)
        anc = anchors()
        for i in range(mine.OutlineCount()):
            if any(mine.Contains(a, i) for a in anc):
                continue                           # reachable through a via or THT pad
            bb = mine.Outline(i).BBox()
            spot = None
            step = 500000
            y = bb.GetTop() + step
            while y < bb.GetBottom() and spot is None:
                x = bb.GetLeft() + step
                while x < bb.GetRight():
                    pt = pcbnew.VECTOR2I(x, y)
                    if inside(mine, pt, i) and inside(other, pt):
                        spot = pt; break
                    x += step
                y += step
            if spot is None:
                print(f'  !! island on {b.GetLayerName(L)} near ({bb.GetCenter().x/1e6-100:.1f},{bb.GetCenter().y/1e6-50:.1f}) mm has no via spot')
                continue
            v = pcbnew.PCB_VIA(b); v.SetPosition(spot); v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetDrill(300000); v.SetWidth(600000); v.SetNetCode(gnd); b.Add(v); added += 1
    if not added:
        break
    print(f'  round {rnd+1}: {added} island via(s) added')
print('  tracks:', len(list(b.GetTracks())))
b.Save('$PCB')
PY

echo "== verify =="
$KC pcb drc --severity-error --exit-code-violations -o drc.rpt "$PCB" \
  && echo "  routed, zero errors, zero unconnected" \
  || { echo "  !! see drc.rpt"; exit 1; }
$KC pcb drc --severity-all -o drc-full.rpt "$PCB" >/dev/null 2>&1 || true
echo "  warnings: $(grep -c '^\[' drc-full.rpt || true)  (drc-full.rpt)"
