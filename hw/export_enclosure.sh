#!/bin/bash
# Export the unit enclosure: every printed part as STL, plus the renders.
# Run from this directory. Output goes to enclosure/.
set -euo pipefail
SCAD=enclosure.scad
OUT=enclosure
mkdir -p "$OUT"

stl() {   # part, file
  echo "   $2"
  openscad -q --export-format binstl -D "part=\"$1\"" -o "$OUT/$2" "$SCAD"
}

png() {   # part, file, size, camera, extra openscad flags...
  local part=$1 file=$2 size=$3 cam=$4; shift 4
  echo "   $file"
  # extra flags go first: --render takes an optional value and would eat the filename
  openscad -q "$@" -D "part=\"$part\"" -o "$OUT/$file" --imgsize="$size" --camera="$cam" \
    --colorscheme=Tomorrow "$SCAD"
}

echo "== Check =="
openscad -D 'part="tub"' -o /dev/null --export-format binstl "$SCAD" 2>&1 | grep -E "ECHO|WARNING|ERROR|Status" || true

echo "== Print these first =="
stl coupon    coupon.stl
stl template  template.stl
stl clamp     clamp.stl

echo "== Then these =="
stl tub_upper tub-upper.stl
stl tub_lower tub-lower.stl
stl lid       lid.stl
stl cover     cover.stl
stl tub       tub.stl

echo "== Renders =="
png assembled enc-assembled.png 1600,1300 450,-230,450,72,160,25  --projection=p
png open      enc-open.png      1100,1600 72,163,900,72,163,30   --projection=o --viewall
png exploded  enc-exploded.png  1600,1300 470,-230,520,72,165,45  --projection=p
png door      enc-door.png      1400,1500 161,163,1500,161,163,0 --projection=o --viewall
png kit       enc-kit.png       1600,1300 225,-15,0,35,0,0,1700  --projection=o
png tub       enc-tub.png       1600,1300 400,-230,360,74,165,20 --projection=p --viewall --render
png lid       enc-lid.png       1400,1200 330,-220,330,74,100,10 --projection=p --viewall --render
png cover     enc-cover.png     1400,1200 300,-200,300,74,60,10  --projection=p --viewall --render

echo "== Illustrations =="
if python3 -c "import PIL, numpy" 2>/dev/null; then
  python3 annotate_enclosure.py
else
  echo "   skipped: needs python3 with Pillow and numpy"
fi

ls -la "$OUT"
