#!/bin/bash
# Produce the JLCPCB upload zip. Run from this directory.
set -euo pipefail
KC=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
PCB=baybasi-ctrl.kicad_pcb
OUT=fab
REV=$(date +%Y%m%d)

rm -rf "$OUT"; mkdir -p "$OUT"

DRY=${1:-}
echo "== DRC =="
if [ "$DRY" = "--dry-run" ]; then
  $KC pcb drc --severity-error -o "$OUT/drc.rpt" "$PCB" || true
  echo "   (dry run: unrouted nets ignored - NOT safe to order)"
else
  $KC pcb drc --severity-error --exit-code-violations -o "$OUT/drc.rpt" "$PCB" || {
    echo "!! Not ready to fabricate. See $OUT/drc.rpt"
    echo "   'unconnected items' means the board is not routed yet."
    exit 1; }
fi

echo "== Gerbers =="
$KC pcb export gerbers \
  --layers "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts" \
  --no-protel-ext --subtract-soldermask -o "$OUT/" "$PCB"

echo "== Drill =="
$KC pcb export drill --format excellon --drill-origin absolute \
  --excellon-zeros-format decimal --generate-map --map-format gerberx2 -o "$OUT/" "$PCB"

echo "== Zip =="
( cd "$OUT" && zip -q "../baybasi-ctrl-$REV-gerbers.zip" *.gbr *.drl *.gbrjob 2>/dev/null || \
                zip -q "../baybasi-ctrl-$REV-gerbers.zip" * )
echo "ready: baybasi-ctrl-$REV-gerbers.zip"
unzip -l "baybasi-ctrl-$REV-gerbers.zip" | tail -3
