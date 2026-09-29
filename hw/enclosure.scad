// Baybasi pixel wall — per-column unit enclosure, rev B
//
// One box per column. It holds the column's 12-way fused distribution block
// and its controller board, block above board, on the inside of a hinged door.
// Four make a display; two ride on each 16 in door (sheet E-2).
//
// WHY THE BLOCK STANDS ON END.  The block is a DAIER FB-1714 (sold as DaierTek
// B0CGT91KTR). Its two feed studs sit on the centreline at OPPOSITE ENDS, and
// its cover lets a cable reach each stud only through a notch in that end
// wall, so each 6 AWG lug points straight out along the block's long axis.
// Laid across the box the way E-1 sketches it, both feeds leave through the
// side walls: 137.7 of block, plus 16 of lug, 6 of heat-shrink and 14 of
// clamp at each end, and two walls, is 215 mm of box before either cable has
// turned, and two of those do not fit on a 406 mm door. Stood on end, the - feed comes straight in through the
// roof, the + feed straight in through the floor, and the box is 144 wide.
//
// WHY THE BOARD STANDS ON TALL POSTS.  The + feed has to reach the bottom of
// the block from below, and the board is below the block. So the + cable runs
// up the middle of the box UNDER the board, and the board stands on posts tall
// enough to clear it. That, not the block, sets the depth of the box:
// blk_lug_z + half the cable + clearance to the board's solder tails. Measure
// blk_lug_z with a lug on the stud before printing anything big.
//
// Carried forward from rev A, unchanged in intent:
//   - Every external connection is held by the enclosure, not by the PCB.
//     Pulling a lead loads the box, never the board.
//   - The controller half splits at the data leads' centreline, so screwing
//     the cover down clamps all twelve at once. Nothing snaps, nothing is glued.
//   - M3 heat-set inserts, and a coupon printed before the big parts.
// New in rev B:
//   - The feeds are clamped to the tub, not to a cover, so either cover can
//     come off with the door swinging and nothing that carries 60 A moves.
//   - The fuse lid and the controller cover are separate. Changing a fuse
//     never unclamps a data lead, and reflashing never exposes the 60 A side.
//   - Half the column is fed upward and half downward (E-3). The right half of
//     the box serves rows 1-6: its six drops leave through the roof and its six
//     data leads through the right wall. The left half serves rows 7-12: drops
//     down past the board and out through the floor, data through the left
//     wall. Power leaves the ends and data the sides, so the looms part at the
//     box (E-3 note 3).
//   - The data leads are wired straight into J1-J12, as the shopping list
//     plans, and clamped where they cross the wall: ribbed jaws in the tub and
//     the cover, staggered so the cover's screws press each lead into a wave.
//     Rev A's JST housings in the wall are gone. Whichever half sat there,
//     either its lock was out of reach or the leads' genders were wrong.
//   - The controller's 5 V shares fuse R07 (E-1), so there is no tap holder.
//
// PRINT THE COUPON AND THE TEMPLATE FIRST.  The coupon checks the lead clamp,
// both insert sizes, the block-bolt pocket and the feed clamp against real
// parts; the template is a 1:1 outline of the block to lay the real block on.
// Every block dimension below comes from the maker's drawings, not a part in
// hand. The coupon and template cost an hour; the tub costs a day.
//
//   openscad -D 'part="coupon"'    -o coupon.stl    enclosure.scad
//   openscad -D 'part="template"'  -o template.stl  enclosure.scad
//   openscad -D 'part="clamp"'     -o clamp.stl     enclosure.scad   (print 2)
//   openscad -D 'part="tub_upper"' -o tub-upper.stl enclosure.scad   (fits a 220 mm bed)
//   openscad -D 'part="tub_lower"' -o tub-lower.stl enclosure.scad
//   openscad -D 'part="lid"'       -o lid.stl       enclosure.scad
//   openscad -D 'part="cover"'     -o cover.stl     enclosure.scad
//   openscad -D 'part="tub"'       -o tub.stl       enclosure.scad   (one piece, needs 330 mm)
//
// export_enclosure.sh writes all of them, and the renders, to enclosure/.
// Every part is exported in its print orientation. ENCLOSURE.md has the
// print settings, the list of things to measure, and the assembly order.

part = "tub";   // [tub, tub_upper, tub_lower, lid, cover, clamp, coupon, template, kit, assembled, open, exploded, door, illus_closed, illus_open, illus_lead, illus_mount]
step = 3;       // [1, 2, 3] illus_lead: lead laid in, cover coming down, clamped
view = "front"; // [front, back, bolt, screw] illus_mount

/* [MEASURE: fuse block, DAIER FB-1714] */
// DAIER publish two drawings of this block that disagree by up to 2 mm. The
// defaults take the newer "product size" sheet, and the larger height.
blk_l        = 137.7;   // length of the base, - end to + end (older sheet: 138.25)
blk_w        = 85.1;    // width of the base (older sheet: 85.0)
blk_w_cover  = 88.0;    // width over the cover's push latches
blk_h        = 36.5;    // mounting face to the top of the latched cover (newer sheet: 35.7)
blk_hole_px  = 121.0;   // mounting-hole pitch along the length (older sheet: 123.25)
blk_hole_py  = 69.1;    // mounting-hole pitch across (older sheet: 70.0)
blk_stud_in  = 8.35;    // stud centre in from each end; both sheets put it level with the holes
blk_lug_z    = 16.0;    // axis of a 6 AWG lug's barrel on a stud, above the mounting face.
                        // THIS SETS THE BOX DEPTH. Guessed from the end view: ~14 to the stud
                        // seat, ~2 more to the barrel axis. Fit a lug and measure it.
blk_led_from = 45;      // blown-fuse LED column, measured from the - end
blk_led_to   = 122;

/* [MEASURE: cables and loose parts] */
feed_od      = 11.0;    // 6 AWG welding cable over the jacket
feed_squeeze = 0.8;     // the clamp's bore is this much under feed_od
lug_reach    = 16.0;    // 6 AWG lug (ring + barrel) past the block's end face, with the ring on the stud
shrink_len   = 6.0;     // heat-shrink over the barrel, past the barrel
drop_bundle  = 15;      // height left in each drop slot for 12 x 14 AWG silicone
lead_w       = 5.2;     // panel data lead, flat 3 x 22 AWG: width. Calipers on a real lead.
lead_t       = 1.7;     // and thickness
lead_bite    = 0.6;     // how far each jaw rib presses into the lead. Coupon check 1.

/* [MEASURE: controller] */
rj45_h       = 13.5;    // RJ45 above the WIZ850io/USR-ES1 module's PCB (rev A)
sock_h       = 8.5;     // A1L/A1R and M1/M2 sockets, ZX-PM2.54 8.5 mm (BOM)
hdr_spacer   = 2.5;     // plastic body of the male headers under the devkit and the module
pcb_pins     = 3.0;     // THT tails below the board. The + feed passes under them.
term_h       = 9.2;     // J1..J12 above the board (KiCad model of the Phoenix part)
dk_usb_by    = 80.5;    // devkit USB receptacle faces, board y. Third-party devkit: measure.

/* [Board: from baybasi-ctrl.kicad_pcb, do not change] */
pcb_x      = 100;
pcb_y      = 95;
pcb_t      = 1.6;
pcb_holes  = [[4.4, 4.4], [95.6, 4.4], [4.4, 90.6], [95.6, 90.6]];
term_x     = [40.0, 49.2, 58.4, 67.6, 76.8, 86.0];  // J1..J6 (y 6.23) and J7..J12 (y 88.6)
j13        = [6.33, 41.58];     // J13 centre; its wires enter from x = 0
eth        = [14.93, 6.04];     // RJ45 centre x, and its face y
sw1_box    = [22.87, 66.59, 32.75, 79.03];
sw1_poles  = [69.0, 71.54, 74.08, 76.62];           // y of poles 1, 2, SP, SP
dk_rows    = [35.57, 60.97];    // A1L and A1R, 25.40 apart on rev B
dk_w       = 28;                // third-party devkit, ~28 wide (FABRICATION.md)

/* [Box] */
wall       = 2.5;
floor_t    = 3;
top_t      = 2.5;
blk_pad    = 3;         // raised seat under the block: 6 mm of floor over the bolt heads
side_ch    = 24;        // least wire channel beside the block
gap_side   = 22;        // board edge to side wall: lead jaws, and the leads' run to J1-J12
div_t      = 5;         // divider between the fuse half and the controller half
clamp_len  = 14;        // feed clamp, along the cable
feed_gap   = 2;         // + feed to the tips of the board's THT tails
lead_above = 5.4;       // data leads' centreline, which is the tub/cover joint, above the board
head_room  = 2.5;
jaw_len    = 10;        // lead jaws, inward from the side wall
jaw_h      = 3.5;       // jaw bar beyond the groove
lead_pitch = 9.2;        // lead to lead: the J1-J12 terminal pitch, so each lead runs straight
eth_w      = 16;        // Ethernet opening, wide enough to reach the plug latch
eth_hi     = 16;
fillet     = 3;

/* [Fasteners] */
m3_free    = 3.4;
m3_insert  = 4.0;       // M3 x 5.7 heat-set, brass
m3_cbore   = 6.5;
m4_free    = 4.5;
m4_insert  = 5.6;       // M4 x 8 heat-set, brass (feed clamps)
m4_head_af = 7.4;       // M4 hex bolt head across flats, plus clearance (block bolts)
m4_head_t  = 3.0;
door_hole  = 4.5;       // #8 or M4 pan head into the door
boss_d     = 9;

$fn  = 48;
TRIM = 1000;            // oversized solid for splitting at split_z

// ---------------------------------------------------------------- geometry --
// Box frame: X across the door, Y up the door, Z out of the door. The cavity
// floor is Z = 0 and the door is at Z = -floor_t.
blk_z0     = blk_pad;
feed_z     = blk_z0 + blk_lug_z;                     // axis of both feeds
feed_r     = feed_od / 2;
standoff_h = max(5, feed_z + feed_r + feed_gap + pcb_pins);
pcb_top    = standoff_h + pcb_t;
split_z    = pcb_top + lead_above;                  // tub/cover joint and data lead centreline
dk_z       = pcb_top + sock_h + hdr_spacer;         // underside of the devkit and the module
rj45_top   = dk_z + pcb_t + rj45_h;
inner_h    = max(rj45_top, blk_z0 + blk_h) + head_room;

CX       = max(blk_w_cover + 2 * side_ch, pcb_y + 2 * gap_side);
bot_zone = clamp_len + 4;                           // + clamp, below the board
pcb_x0   = (CX - pcb_y) / 2;
pcb_y0   = bot_zone;
div_y0   = pcb_y0 + pcb_x + 1;
div_y1   = div_y0 + div_t;
y_split  = (div_y0 + div_y1) / 2;                   // lid/cover joint, and tub_upper/tub_lower
gal      = lug_reach + shrink_len;                  // gallery: the + lug and its heat-shrink
blk_cx   = CX / 2;
blk_y0   = div_y1 + gal;                            // + end of the block
blk_y1   = blk_y0 + blk_l;                          // - end
blk_ym   = (blk_y0 + blk_y1) / 2;
top_zone = lug_reach + shrink_len + clamp_len + 3;
CY       = blk_y1 + top_zone;
EX       = CX + 2 * wall;
EY       = CY + 2 * wall;
EZ       = floor_t + inner_h + top_t;

// The board sits turned 90 degrees clockwise (seen from the front): J13 at
// the top edge, facing the block that feeds it; J1..J6 and the RJ45 face the
// right wall; J7..J12 and the devkit's USB ports face the left wall.
function B(bx, by) = [pcb_x0 + pcb_y - by, pcb_y0 + pcb_x - bx];

bore_r   = (feed_od - feed_squeeze) / 2;
clamp_sx = feed_r + 5.5;                            // clamp screw, off the cable axis
clamp_w  = 2 * (clamp_sx + 5);

eth_c    = B(eth[0], eth[1]);                       // [face x, centre y]
eth_z    = dk_z + pcb_t + rj45_h / 2;
lead_y   = [for (i = [0:5]) pcb_y0 + pcb_x - term_x[5 - i]];   // J12..J7 left / J6..J1 right, bottom up
jaw_y0   = lead_y[0] - 6;                           // extent of each side's jaw bar
jaw_y1   = lead_y[5] + 6;
drop_up_x = CX - 18;                                // roof slot: the right half's drops, rows 1-6
drop_dn_x = 18;                                     // floor slot: the left half's drops, rows 7-12
drop_z0  = split_z - drop_bundle - 8;               // bottom of each drop slot
dn_lo    = 4.5 + boss_d / 2;                        // the rows 7-12 drops pass the board between the
dn_hi    = B(4.4, 90.6)[0] - 3.5;                   //   cover's corner screw and the board's post
j13_x    = B(j13[0], j13[1])[0];                    // J13's leads cross the divider here
notch_x  = [min(blk_cx - feed_r - 2, j13_x - 7), max(blk_cx + feed_r + 2, j13_x + 7)];
dip_lo   = B(sw1_box[2] + 1.8, sw1_box[3] + 1.5);   // DIP window corners
dip_hi   = B(sw1_box[0] - 1.8, sw1_box[1] - 1.5);

cover_screws = [[4.5, 4.5], [CX - 4.5, 4.5], [4.5, div_y0 - 2.5], [CX - 4.5, div_y0 - 2.5]];
lid_screws   = [[4.5, blk_y0 + 4], [CX - 4.5, blk_y0 + 4],
                [4.5, (div_y1 + CY) / 2], [CX - 4.5, (div_y1 + CY) / 2],
                [4.5, CY - 4.5], [CX - 4.5, CY - 4.5]];
join_screws  = [36, CX - 20];                       // tub_upper to tub_lower, through the divider;
                                                    // the left one clear of the rows 7-12 drops
blk_holes    = [for (sx = [-1, 1], sy = [-1, 1])
                    [blk_cx + sx * blk_hole_py / 2, blk_ym + sy * blk_hole_px / 2]];
door_holes   = [[blk_cx - 30, CY - 10], [blk_cx + 30, CY - 10],
                [blk_cx + 25, div_y1 + 11], [CX - 12, div_y1 + 11],
                [pcb_x0 + 22, pcb_y0 + 50], [pcb_x0 + 73, pcb_y0 + 50],
                [blk_cx - 30, 9], [blk_cx + 30, 9]];

echo(str("Box ", EX, " x ", EY, " x ", EZ, " mm (w x h x d). Board posts ", standoff_h,
         " mm. Tub halves ", y_split + wall, " and ", EY - y_split - wall, " mm tall."));

// Design rules. A measurement that makes two printed features collide stops
// the build rather than quietly printing a box something does not fit in.
// Loose parts on flexible leads only get a warning: they can sit elsewhere.
assert(eth_z - eth_hi / 2 > split_z + 1, "Ethernet opening reaches below the cover joint");
assert(jaw_y0 > cover_screws[0][1] + boss_d / 2, "lead jaws hit the cover's lower corner screw");
assert(jaw_y1 < min(cover_screws[2][1] - boss_d / 2, eth_c[1] - eth_w / 2),
       "lead jaws hit the cover's upper corner screw or the Ethernet opening");
assert(jaw_len + 6 < pcb_x0 + pcb_y - 93.15, "lead jaws leave no room to land the leads in J7-J12");
assert(eth_c[1] + eth_w / 2 < cover_screws[3][1] - boss_d / 2 + 1,
       "Ethernet opening cuts into the cover's corner screw");
assert(drop_up_x - 8 > blk_cx + blk_w_cover / 2 - 2, "roof drop slot is not over the right channel");
assert(drop_dn_x - 8 > cover_screws[0][0] + boss_d / 2 && drop_dn_x + 8 < blk_cx - clamp_w / 2,
       "floor drop slot hits a corner screw or the + feed clamp");
assert(dn_hi - dn_lo >= 12, "no room for the rows 7-12 drops between the cover screw and the board post");
if (lid_screws[0][1] + boss_d / 2 > blk_y1 - 115 - 4)
    echo("WARNING: a lid screw boss sits beside the lowest drop terminals");

// ------------------------------------------------------------------ pieces --
module shell(z0, z1) {
    translate([-wall, -wall, z0])
        hull() for (x = [fillet, EX - fillet], y = [fillet, EY - fillet])
            translate([x, y, 0]) cylinder(r = fillet, h = z1 - z0);
}

module cavity(z0, z1) {
    translate([0, 0, z0]) cube([CX, CY, z1 - z0]);
}

// The data lead clamps. Each lead lies flat in a groove centred on the
// tub/cover joint, so the tub holds its lower half and the cover its upper.
// Past the wall, each side has a jaw bar jaw_len deep. Ribs across the groove
// stand lead_bite proud, the tub's and the cover's offset by half a step, so
// screwing the cover down presses every lead on that side into a wave. A tug
// has to drag the lead through the wave, and the terminal never feels it.
// Drawn for the left wall: wall inner face at x = 0, the joint at z = 0.
// half = -1 is the tub's side of the joint, +1 the cover's.
module jaw_bar(half) {
    zb = half * (lead_t / 2 + jaw_h);
    translate([0, jaw_y0, min(0, zb)]) cube([jaw_len, jaw_y1 - jaw_y0, abs(zb)]);
    // 45-degree gusset on the face away from the joint: prints without support
    translate([0, jaw_y1, 0]) rotate([90, 0, 0]) linear_extrude(jaw_y1 - jaw_y0)
        polygon([[0, zb - half * 0.01], [jaw_len, zb - half * 0.01], [0, zb + half * jaw_len]]);
}

module lead_cut() {                          // one lead's groove, through wall and jaw
    translate([-wall - 1, -(lead_w + 0.4) / 2, -lead_t / 2]) cube([wall + jaw_len + 2, lead_w + 0.4, lead_t]);
    hull() {                                 // chamfered mouth: the lead bends here, not on an edge
        translate([-wall - 0.01, -(lead_w + 0.4) / 2 - 1.2, -lead_t / 2 - 1.2])
            cube([0.01, lead_w + 2.8, lead_t + 2.4]);
        translate([-wall + 1.2, -(lead_w + 0.4) / 2, -lead_t / 2]) cube([0.01, lead_w + 0.4, lead_t]);
    }
}

module lead_ribs(half) {                     // the tub's ribs point up, the cover's down
    for (x = half < 0 ? [2.5, 6.5] : [4.5, 8.5])
        translate([x, (lead_w + 0.4) / 2, half * lead_t / 2]) rotate([90, 0, 0])
            linear_extrude(lead_w + 0.4)
                polygon([[-0.8, half * 0.01], [0.8, half * 0.01], [0, -half * lead_bite]]);
}

module on_sides() {                          // left wall as drawn, right wall mirrored
    translate([0, 0, split_z]) children();
    translate([CX, 0, split_z]) mirror([1, 0, 0]) children();
}

module on_side_leads() {                     // J12..J7 left, J6..J1 right, bottom up
    on_sides() for (y = lead_y) translate([0, y, 0]) children();
}

// A U-slot through a wall that runs along X (the roof or the floor), round at
// the bottom. w wide, bottom at z_bot.
module u_slot(x, y0, y1, w, z_bot) {
    hull() {
        translate([x, y0, z_bot + w / 2]) rotate([-90, 0, 0]) cylinder(d = w, h = y1 - y0);
        translate([x - w / 2, y0, split_z + 1]) cube([w, y1 - y0, TRIM]);
    }
}

// Tie-down: a block with a slot for a cable tie. along = direction the tie runs.
module tie_anchor(p, along = "x") {
    translate([p[0], p[1], 0]) rotate([0, 0, along == "x" ? 0 : 90]) difference() {
        translate([-6, -3, 0]) cube([12, 6, 6]);
        translate([-7, -2, 1.4]) cube([14, 4, 2.4]);
    }
}

// Feed clamp, drawn at the bottom wall with the cable leaving along -y. The
// cradle is part of the tub; the clamp is its own part and screws down onto
// it. Their bores meet at feed_od - feed_squeeze, with ridges to bite.
module bore_ridges(len) {
    for (t = [0.25, 0.5, 0.75]) translate([0, t * len, 0]) rotate([-90, 0, 0])
        difference() {
            cylinder(r = bore_r + 0.1, h = 1.2, center = true);
            cylinder(r = bore_r - 0.5, h = 2, center = true);
        }
}

module cradle() {
    difference() {
        translate([blk_cx - clamp_w / 2, 0, 0]) cube([clamp_w, clamp_len, feed_z]);
        translate([blk_cx, -1, feed_z]) rotate([-90, 0, 0]) cylinder(r = bore_r, h = clamp_len + 2);
        for (s = [-1, 1]) translate([blk_cx + s * clamp_sx, clamp_len / 2, feed_z - 8.5])
            cylinder(d = m4_insert, h = 9);
    }
    intersection() {
        translate([blk_cx, 0, feed_z]) bore_ridges(clamp_len);
        translate([blk_cx - clamp_w / 2, 0, 0]) cube([clamp_w, clamp_len, feed_z]);
    }
}

module clamp_solid() {
    difference() {
        union() {
            translate([blk_cx - clamp_w / 2, 0.3, feed_z]) cube([clamp_w, clamp_len - 0.3, split_z - feed_z]);
            // tongue: fills the wall slot above the cable
            translate([blk_cx - feed_r - 0.1, -wall, feed_z]) cube([feed_od + 0.2, wall + 0.4, split_z - feed_z]);
        }
        translate([blk_cx, -wall - 1, feed_z]) rotate([-90, 0, 0]) cylinder(r = bore_r, h = clamp_len + wall + 2);
        for (s = [-1, 1]) translate([blk_cx + s * clamp_sx, clamp_len / 2, 0]) {
            cylinder(d = m4_free, h = TRIM);
            translate([0, 0, split_z - 4]) cylinder(d = 8.5, h = TRIM);
        }
    }
    intersection() {
        translate([blk_cx, 0, feed_z]) bore_ridges(clamp_len);
        translate([blk_cx - clamp_w / 2, 0.3, feed_z]) cube([clamp_w, clamp_len - 0.3, split_z - feed_z]);
    }
}

module feed_slot() {                          // through the bottom wall, bell-mouthed outside
    u_slot(blk_cx, -wall - 1, 1, feed_od + 0.6, feed_z - feed_r - 0.3);
    translate([blk_cx, -wall - 0.01, feed_z]) rotate([90, 0, 0])
        cylinder(r1 = feed_r + 0.3, r2 = feed_r + 2.3, h = 2.01);
}

// The same features at the roof: mirror the floor's.
module at_top() { translate([0, CY, 0]) mirror([0, 1, 0]) children(); }

// ------------------------------------------------------------------ the tub --
module tub_solid() {
    difference() {
        union() {
            difference() {
                shell(-floor_t, split_z);
                cavity(0, split_z + 1);
            }
            // raised seat under the block
            translate([blk_cx - blk_w / 2 - 2, blk_y0 - 2, 0]) cube([blk_w + 4, blk_l + 4, blk_pad]);
            // divider between the fuse half and the controller half
            translate([0, div_y0, 0]) cube([CX, div_t, split_z]);
            // board posts
            for (h = pcb_holes) translate(concat(B(h[0], h[1]), 0)) cylinder(d = 7, h = standoff_h);
            // feed cradles, + at the floor and - at the roof
            cradle();
            at_top() cradle();
            // guides that hold the + feed on its line under the board
            for (y = [pcb_y0 + 30, pcb_y0 + 70]) translate([blk_cx - 11, y, 0]) cube([22, 3, feed_z]);
            on_sides() jaw_bar(-1);
            for (p = concat(cover_screws, lid_screws)) translate([p[0], p[1], 0]) cylinder(d = boss_d, h = split_z);
            for (x = join_screws) translate([x - 4.5, div_y0 - 8, 0]) cube([9, 8, 12.5]);
            // cable ties: rows 1-6 drops up the right channel, rows 7-12 down the
            // left one and on past the board to the floor slot
            for (p = [[CX - 12, CY - 26], [CX - 12, blk_y0 + 60], [12, blk_y0 + 60], [(dn_lo + dn_hi) / 2, 12]])
                tie_anchor(p, "x");
            eth_tie();
        }
        on_side_leads() lead_cut();
        // the + and - feeds
        feed_slot();
        at_top() feed_slot();
        // drops: rows 1-6 out of the roof, rows 7-12 out of the floor
        u_slot(drop_up_x, CY - 1, CY + wall + 1, 16, drop_z0);
        u_slot(drop_dn_x, -wall - 1, 1, 16, drop_z0);
        for (y = [pcb_y0 + 30, pcb_y0 + 70])
            translate([blk_cx, y - 1, feed_z]) rotate([-90, 0, 0]) cylinder(r = feed_r + 0.6, h = 5);
        // divider notches: the + feed below with J13's two leads above it, and
        // the rows 7-12 drops on their way down to the floor slot
        translate([notch_x[0], div_y0 - 1, feed_z - feed_r - 1]) cube([notch_x[1] - notch_x[0], div_t + 2, TRIM]);
        translate([dn_lo + 0.5, div_y0 - 1, 8]) cube([dn_hi - dn_lo - 0.9, div_t + 2, TRIM]);
        // block bolts: hex heads captive in the back of the floor
        for (p = blk_holes) translate([p[0], p[1], -floor_t - 1]) {
            cylinder(d = 4.4, h = floor_t + blk_pad + 2);
            cylinder(d = m4_head_af / cos(30), h = m4_head_t + 1, $fn = 6);
        }
        for (h = pcb_holes) translate(concat(B(h[0], h[1]), standoff_h - 6)) cylinder(d = m3_insert, h = 7);
        // 9 deep: an M3 x 12 through the cover's 6 mm under its head runs the full
        // 5.7 mm insert and still stops 3 mm short of the bottom of the hole
        for (p = concat(cover_screws, lid_screws)) translate([p[0], p[1], split_z - 9]) cylinder(d = m3_insert, h = 10);
        // tub_upper to tub_lower: insert pressed into the lower half from the
        // split face, screw from the gallery through the upper half
        for (x = join_screws) translate([x, 0, 8]) rotate([-90, 0, 0]) {
            translate([0, 0, y_split - 7]) cylinder(d = m3_insert, h = 7.01);
            translate([0, 0, y_split]) cylinder(d = m3_free, h = div_t);
        }
        for (p = door_holes) translate([p[0], p[1], -floor_t - 1]) cylinder(d = door_hole, h = floor_t + blk_pad + 2);
        tub_vents();
        translate([-EX, -EY, split_z]) cube([3 * EX, 3 * EY, TRIM]);
    }
    on_side_leads() lead_ribs(-1);
}

// Vertical slots in the floor and roof walls, either side of each feed clamp.
vent_x = [for (i = [0:3]) drop_dn_x + 12 + 6 * i, for (i = [0:3]) drop_up_x - 12 - 6 * i];

module tub_vents() {
    for (y = [-wall - 1, CY - 1], x = vent_x)
        translate([x - 1.5, y, 5]) cube([3, wall + 2, split_z - 10]);
}

// Tie lug under the Ethernet opening. The lead leaves the opening, turns down
// the side of the box, and a cable tie through this lug's slot holds it
// there, so a pull on the lead loads the box instead of the module's socket
// pins (rev A's cable_clamp, moved up to where the lead actually runs). The
// 45-degree underside prints without support.
module eth_tie() {
    x0 = CX + wall - 0.5;
    z1 = split_z - 1.5;
    z0 = z1 - 12;
    difference() {
        hull() {
            translate([x0, eth_c[1] - 8, z0]) cube([8.5, 16, z1 - z0]);
            translate([x0, eth_c[1] - 8, z0 - 8]) cube([0.5, 16, 1]);
        }
        translate([x0 + 3.2, eth_c[1] - 2.6, z0 - 10]) cube([2.8, 5.2, 30]);
    }
}

// ----------------------------------------------------------- lid and cover --
module cap_full() {
    difference() {
        shell(split_z, inner_h + top_t);
        cavity(split_z - 1, inner_h);
    }
}

module cap_sleeves(pts) {
    for (p = pts) translate([p[0], p[1], split_z]) cylinder(d = boss_d, h = inner_h - split_z + 0.01);
}

module cap_screw_holes(pts) {
    for (p = pts) translate([p[0], p[1], split_z - 1]) {
        cylinder(d = m3_free, h = TRIM);
        translate([0, 0, 7]) cylinder(d = m3_cbore, h = TRIM);
    }
}

module engrave(txt, p, size = 3.2, halign = "center", rot = 0) {
    translate([p[0], p[1], inner_h + top_t - 0.6]) rotate([0, 0, rot])
        linear_extrude(1) text(txt, size = size, halign = halign, valign = "center",
                               font = "Liberation Sans:style=Bold");
}

module face_slots(y, x0, x1) {                          // vent slots in a cap's face
    translate([x0, y - 1.5, inner_h - 1]) cube([x1 - x0, 3, top_t + 2]);
}

// The fuse lid: the block, its gallery and the roof. Six screws.
module lid_solid() {
    difference() {
        union() {
            difference() {                       // the cap above the joint
                cap_full();
                translate([-EX, y_split - 2 * EY, -TRIM / 2]) cube([3 * EX, 2 * EY, TRIM]);
            }
            translate([0, y_split, split_z]) cube([CX, div_y1 - y_split, inner_h - split_z + 0.01]);
            cap_sleeves(lid_screws);
            // tongue that closes the roof drop slot down to the bundle
            translate([drop_up_x - 7.9, CY - 0.4, drop_z0 + drop_bundle])
                cube([15.8, wall + 0.4, split_z - drop_z0 - drop_bundle]);
            spare_fuses();
        }
        cap_screw_holes(lid_screws);
        // J13's leads cross the divider just under the joint
        translate([notch_x[0], div_y0 - 1, split_z - 1]) cube([notch_x[1] - notch_x[0], div_t + 2, 5]);
        // blown-fuse LEDs, seen without opening anything
        translate([blk_cx - 5, blk_y1 - blk_led_to, inner_h - 1]) cube([10, blk_led_to - blk_led_from, top_t + 2]);
        for (y = [div_y1 + 3, div_y1 + 9, CY - 5, CY - 10])
            face_slots(y, 22, CX - 22);
        engrave("FUSES", [blk_cx + 18, blk_ym + 40], 5, rot = 90);
        engrave("12 x 20 A", [blk_cx - 18, blk_ym + 40], 3.6, rot = 90);
        engrave("- FEED", [blk_cx, CY - 26], 3.6);
    }
}

// Spare ATC fuses and the puller live on the inside of the lid, over the
// - lug, where there is depth to spare.
module spare_fuses() {
    translate([blk_cx - 29, CY - 40, inner_h - 12]) difference() {
        cube([58, 24, 12.01]);
        for (i = [0:3]) translate([4 + 9.2 * i, 2, -1]) cube([5.6, 19.6, 11]);
        translate([42, 2, -1]) cube([12, 19.6, 11]);
    }
}

// The controller cover: clamps the twelve data leads, closes the floor drop
// slot, and carries the Ethernet opening and the DIP window. Four screws.
module cover_solid() {
    difference() {
        union() {
            difference() {                       // the cap below the joint
                cap_full();
                translate([-EX, y_split, -TRIM / 2]) cube([3 * EX, 2 * EY, TRIM]);
            }
            translate([0, div_y0, split_z]) cube([CX, y_split - div_y0, inner_h - split_z + 0.01]);
            cap_sleeves(cover_screws);
            on_sides() jaw_bar(1);
            // collar round the DIP window
            translate([dip_lo[0] - 1.6, dip_lo[1] - 1.6, inner_h - 6])
                cube([dip_hi[0] - dip_lo[0] + 3.2, dip_hi[1] - dip_lo[1] + 3.2, 6.01]);
        }
        on_side_leads() lead_cut();
        cap_screw_holes(cover_screws);
        translate([notch_x[0], div_y0 - 1, split_z - 1]) cube([notch_x[1] - notch_x[0], div_t + 2, 5]);
        // Ethernet: the lead plugs straight into the module through this opening
        translate([CX - 1, eth_c[1] - eth_w / 2, eth_z - eth_hi / 2]) cube([wall + 2, eth_w, eth_hi]);
        // DIP window: set the column with a pick, read it without opening the box
        translate([dip_lo[0], dip_lo[1], inner_h - 7]) cube([dip_hi[0] - dip_lo[0], dip_hi[1] - dip_lo[1], TRIM]);
        for (y = [7, 12, div_y0 - 12, div_y0 - 7])
            face_slots(y, 22, CX - 22);
        cover_labels();
        translate([-EX, -EY, split_z - TRIM]) cube([3 * EX, 3 * EY, TRIM]);
    }
    on_side_leads() lead_ribs(1);
    // tongue that closes the floor drop slot down to the bundle
    translate([drop_dn_x - 7.9, -wall, drop_z0 + drop_bundle])
        cube([15.8, wall + 0.4, split_z - drop_z0 - drop_bundle]);
}

module cover_labels() {
    for (i = [0:5]) {
        engrave(str("J", 12 - i), [7.5, lead_y[i]], 2.6);
        engrave(str("J", 6 - i),  [CX - 7.5, lead_y[i]], 2.6);
    }
    engrave("ETH", [CX - 7.5, eth_c[1]], 2.6);
    // SW1 poles run right to left: 1, 2, SP, SP. The legend is the board's own.
    for (i = [0:1]) engrave(str(i + 1), [B(0, sw1_poles[i])[0], dip_hi[1] + 4], 2.6);
    engrave("COL=2+1  ON=1", [(dip_lo[0] + dip_hi[0]) / 2, dip_lo[1] - 4.5], 2.6);
    engrave("+ FEED", [blk_cx, bot_zone - 7], 3.6);
    engrave("BAYBASI COLUMN CTRL revB", [blk_cx + 8, pcb_y0 + 40], 3.2, rot = 90);
}

// ------------------------------------------------------------ the clamp part --
module clamp() { clamp_solid(); }

// ---------------------------------------------------------------- the coupon --
// Prints in about 40 minutes. Clamp a real data lead in the jaw pair, fit an
// M3 and an M4 insert, an M4 hex bolt from underneath, and a length of the
// actual 6 AWG under a printed clamp. Adjust the parameters named in
// ENCLOSURE.md before committing to the tub.
//
// Two leads' worth of side wall and jaw, one half of the joint. The tub half
// is thickened to take two M3 inserts; the cover half takes the screws.
module jaw_test(half) {
    y0 = -10;
    y1 = lead_pitch + 10;
    zb = half < 0 ? -8 : 0;
    zt = half < 0 ? 0 : lead_t / 2 + jaw_h;
    difference() {
        translate([-wall, y0, zb]) cube([wall + jaw_len, y1 - y0, zt - zb]);
        for (y = [0, lead_pitch]) translate([0, y, 0]) lead_cut();
        for (y = [y0 + 4, y1 - 4]) translate([jaw_len / 2 - wall / 2, y, zb - 1])
            cylinder(d = half < 0 ? m3_insert : m3_free, h = zt - zb + 2);
    }
    for (y = [0, lead_pitch]) translate([0, y, 0]) lead_ribs(half);
}

module coupon() {
    // (1) the lead clamp: both halves, joint face up. Screw them together
    // over a real lead, the tub half's ribs between the cover half's.
    translate([-8 + wall, 8, 8]) jaw_test(-1);
    translate([6.5 + wall, 17.2, lead_t / 2 + jaw_h]) rotate([180, 0, 0]) jaw_test(1);
    // (2) M3 insert: lid, cover, board posts
    translate([32, 6, 0]) difference() {
        cylinder(d = boss_d, h = 9);
        translate([0, 0, 2.5]) cylinder(d = m3_insert, h = 7);
    }
    // (3) block bolt: M4 hex head captive from below, 6 mm of floor like the tub
    translate([40, -2, 0]) difference() {
        cube([18, 18, floor_t + blk_pad]);
        translate([9, 9, -1]) {
            cylinder(d = 4.4, h = 10);
            cylinder(d = m4_head_af / cos(30), h = m4_head_t + 1, $fn = 6);
        }
    }
    // (4) a feed cradle with its two M4 inserts; print one clamp to go on it
    translate([62 + clamp_w / 2 - blk_cx, 0, 0]) cradle();
}

// -------------------------------------------------------------- the template --
// 1:1 outline of the block, 1.2 mm thick. Stand the real block on it: the
// outline and all four bolt holes must line up. The spine runs past both ends
// on the centreline, which is where the feed clamps assume the two studs are;
// sight each stud along it.
module template() {
    t = 1.2;
    difference() {
        union() {
            difference() {
                translate([-blk_w / 2, -blk_l / 2, 0]) cube([blk_w, blk_l, t]);
                translate([-blk_w / 2 + 4, -blk_l / 2 + 4, -1]) cube([blk_w - 8, blk_l - 8, t + 2]);
            }
            for (sx = [-1, 1], sy = [-1, 1]) hull() {
                translate([sx * blk_hole_py / 2, sy * blk_hole_px / 2, 0]) cylinder(d = 10, h = t);
                translate([sx * blk_hole_py / 2, 0, 0]) cylinder(d = 4, h = t);
            }
            for (sy = [-1, 1]) translate([-blk_hole_py / 2, sy * blk_hole_px / 2 - 2, 0]) cube([blk_hole_py, 4, t]);
            translate([-2, -blk_l / 2 - 14, 0]) cube([4, blk_l + 28, t]);
            for (sy = [-1, 1]) translate([-9, sy * (blk_l / 2 + 8) - 6, 0]) cube([18, 12, t]);
        }
        for (sx = [-1, 1], sy = [-1, 1]) translate([sx * blk_hole_py / 2, sy * blk_hole_px / 2, -1])
            cylinder(d = 4.3, h = t + 2);
        for (s = [["-", 1], ["+", -1]])
            translate([0, s[1] * (blk_l / 2 + 8), t - 0.5])
                linear_extrude(1) text(s[0], size = 8, halign = "center", valign = "center",
                                       font = "Liberation Sans:style=Bold");
    }
}

// ------------------------------------------------------------------ ghosts --
// Rough stand-ins for the parts that go in the box, for the renders only.
module ghost_block() {
    base_h = 16;
    translate([blk_cx, 0, blk_z0]) {
        color("#2b2b2b") translate([-blk_w / 2, blk_y0, 0]) cube([blk_w, blk_l, base_h]);
        // fuses: two rows of six, blades across the block
        for (i = [0:5], s = [-1, 1]) {
            y = blk_y1 - 52 - 12.6 * i;
            color(["#e0b400", "#d62828", "#1d6fd6", "#e0b400", "#d62828", "#1d6fd6"][i])
                translate([s * 20 - 9.5, y - 2.5, base_h]) cube([19, 5, 11]);
            color("#ff3b30") translate([s * 5, y, base_h]) cylinder(d = 3, h = 1.5);
            color("#c9c9c9") translate([s * 36, y, base_h]) cylinder(d = 7, h = 3);
        }
        // negative bus
        for (i = [0:2], s = [-1, 1], c = [23, 34])
            color("#c9c9c9") translate([s * (12 + 10 * i), blk_y1 - c, base_h]) cylinder(d = 6, h = 3);
        // studs and lugs
        for (e = [[blk_y0 + blk_stud_in, -1], [blk_y1 - blk_stud_in, 1]]) {
            color("#bdbdbd") translate([0, e[0], base_h - 2]) cylinder(d = 5, h = 12);
            color("#c98a4b") hull() {
                translate([0, e[0], blk_lug_z - 1]) cylinder(d = 11, h = 2);
                translate([0, e[0] + e[1] * (blk_stud_in + lug_reach), blk_lug_z])
                    rotate([90, 0, 0]) cylinder(d = 9, h = 0.1, center = true);
            }
        }
        if (is_undef($block_cover) || $block_cover)       // the block's own clear cover
            color("white", 0.28) translate([-blk_w_cover / 2, blk_y0, base_h - 3])
                cube([blk_w_cover, blk_l, blk_h - base_h + 3]);
    }
}

// Both feeds come up from the supply at the foot of the wall. The + goes
// straight up into the floor clamp. The block's - stud is at its top end, so
// the - climbs the left side of the box, clear of the rows 1-6 drops leaving
// the right of the roof, and bends over into the roof clamp.
feed_bend = 46;                                     // - feed's bend radius over the roof
function minus_route(tail = 150) = let(yt = CY + wall + 12)
    concat([[blk_cx, blk_y1 + lug_reach + shrink_len, feed_z], [blk_cx, yt, feed_z]],
           [for (a = [15 : 15 : 165]) [blk_cx - feed_bend + feed_bend * cos(a), yt + feed_bend * sin(a), feed_z]],
           [[blk_cx - 2 * feed_bend, yt, feed_z], [blk_cx - 2 * feed_bend, -wall - tail, feed_z]]);

module ghost_feeds(tail = 150) {
    wire(minus_route(tail), feed_od, "#111");
    color("#111") translate([blk_cx, blk_y0 - lug_reach, feed_z]) rotate([90, 0, 0])
        cylinder(d = feed_od, h = blk_y0 - lug_reach + wall + tail);
    color("#303030") for (e = [[blk_y1 + lug_reach, 1], [blk_y0 - lug_reach, -1]])
        translate([blk_cx, e[0] + (e[1] > 0 ? 0 : -shrink_len), feed_z]) rotate([-90, 0, 0])
            cylinder(d = feed_od + 1, h = shrink_len);
}

module ghost_drops() {
    // rows 1-6: twelve wires up the right channel and out of the roof
    for (i = [0:3], j = [0:2]) color((i + j) % 2 == 0 ? "#b3261e" : "#1e1e1e")
        translate([drop_up_x - 5 + 3.4 * i, blk_y0 + 20, drop_z0 + 4.5 + 3.4 * j])
            rotate([-90, 0, 0]) cylinder(d = 3.2, h = CY - blk_y0 - 20 + wall + 40, $fn = 12);
    // rows 7-12: twelve down the left channel, past the board, out of the floor
    for (i = [0:2], j = [0:3]) color((i + j) % 2 == 0 ? "#b3261e" : "#1e1e1e")
        translate([(dn_lo + dn_hi) / 2 - 3.4 + 3.4 * i, -wall - 40, drop_z0 + 3 + 3.4 * j])
            rotate([-90, 0, 0]) cylinder(d = 3.2, h = blk_y1 - 20 + wall + 40, $fn = 12);
}

module ghost_board() {
    // board
    color("#1f6f43") translate([pcb_x0, pcb_y0, standoff_h]) cube([pcb_y, pcb_x, pcb_t]);
    // J1..J12 and J13
    for (x = term_x) {
        color("#2e8b57") translate(concat(B(x + 3.9, 9.4), pcb_top)) cube([7.7, 7.8, term_h]);
        color("#2e8b57") translate(concat(B(x + 3.9, 93.15), pcb_top)) cube([7.7, 7.8, term_h]);
    }
    color("#2e8b57") translate(concat(B(11.58, 46.71), pcb_top)) cube([10.3, 9.9, 10]);
    // devkit and its sockets
    color("#111") for (r = dk_rows) translate(concat(B(r + 1.3, 70.34 + 1.3), pcb_top)) cube([56, 2.6, sock_h]);
    color("#20252b") translate(concat(B((dk_rows[0] + dk_rows[1]) / 2 + dk_w / 2, dk_usb_by), dk_z))
        cube([dk_usb_by - 15.9, dk_w, pcb_t]);
    color("#b8b8b8") translate(concat(B((dk_rows[0] + dk_rows[1]) / 2 + 9, 34.5), dk_z + pcb_t))
        cube([18, 18, 3.2]);
    for (d = [-6.5, 6.5]) color("#9a9a9a")
        translate(concat(B((dk_rows[0] + dk_rows[1]) / 2 + d + 4.5, dk_usb_by + 0.5), dk_z + pcb_t))
            cube([7.5, 9, 3.2]);
    // Ethernet module and its jack
    color("#1b4f8a") translate(concat(B(26.99, 34.16), dk_z)) cube([26.1, 24.1, pcb_t]);
    color("#c0c0c0") translate([eth_c[0] - 21, B(23.04, 0)[1], dk_z + pcb_t]) cube([21, 16.2, rj45_h]);
    color("#111") for (m = [[3.45, 13.68, 6.09, 29.02], [23.77, 13.68, 26.41, 29.02]])      // M1, M2
        translate(concat(B(m[2], m[3]), pcb_top)) cube([m[3] - m[1], m[2] - m[0], sock_h]);
    for (u = [15, 45]) {                                                              // U1, U2
        color("#2a2a2a") translate(concat(B(81.33, u + 26), pcb_top)) cube([26, 9.8, 4]);
        color("#141414") translate(concat(B(80.1, u + 25.4), pcb_top + 4)) cube([24.8, 7.4, 3.6]);
    }
    // SW1, C1
    color("#d62828") translate(concat(B(sw1_box[2], sw1_box[3]), pcb_top)) cube([12.44, 9.88, 6.5]);
    color("#1a1a1a") translate(concat(B(6.78 + 1.75, 66.7), pcb_top)) cylinder(d = 8, h = 12.5);
}

module ghosts() {
    ghost_block(); ghost_feeds(); ghost_drops(); ghost_board(); ghost_leads(outside = false);
}

module clamp_pair() {
    color("#e8e8e8") { clamp_solid(); at_top() clamp_solid(); }
}

module unit_closed() {
    color(PRINT) tub_solid();
    clamp_pair();
    color("#d9d3c7") lid_solid();
    color("#e0dbd0") cover_solid();
}

// ----------------------------------------------------------- illustrations --
// Scenes for the illustrated guide: the unit standing on a door the way you
// meet it with the door open, with stand-ins for everything that goes in it
// and the cables that leave it. Nothing here is printed. Each scene echoes the
// 3D points its labels point at; annotate_enclosure.py turns those into
// callouts on the render.

function U(p) = [p[0], -p[2], p[1]];               // box frame -> upright, Z up
module upright() { rotate([90, 0, 0]) children(); }
module anchor(name, p, up = true) {
    q = up ? U(p) : p;
    echo(str("ANCHOR|", name, "|", q[0], "|", q[1], "|", q[2]));
}

// Cutaways: with $slab = [corner, size] set, each part is cut inside its own
// colour, so the cut faces keep it. Without $slab, clip() does nothing.
module clip() {
    if (is_undef($slab)) children();
    else intersection() { translate($slab[0]) cube($slab[1]); children(); }
}

module wire(pts, d = 1.7, c = "#222") {
    color(c) clip() for (i = [0 : len(pts) - 2]) hull() {
        translate(pts[i]) sphere(d = d, $fn = 10);
        translate(pts[i + 1]) sphere(d = d, $fn = 10);
    }
}

DOOR_T  = 18;
STEEL   = "#8e959c";
LID_C   = "#cad8e6";                               // the renders tint the lid and cover so you can
COVER_C = "#e8d9b0";                               // tell them apart; they print in one colour
DOOR_C  = "#b8915f";
module ghost_door(x0, x1, y0, y1) {
    color(DOOR_C) clip() translate([x0, y0, -floor_t - DOOR_T]) cube([x1 - x0, y1 - y0, DOOR_T]);
}

// The twelve data leads: flat 3 x 22 AWG, wired straight into J1-J12 (the
// shopping list's plan). Each crosses the wall in its jaws, waving over the
// tub's ribs and under the cover's. Inside, green and white go into the
// terminal and red, the panel's own 5 V, is cut back under heat-shrink.
// Outside, rows 1-6 turn up the right side of the box and rows 7-12 down the
// left, each lead running outside the ones it passes.
LEAD = ["#c0392b", "#2e8b57", "#f2f2f2"];          // 5 V (cut back), data, 0 V

module ghost_leads(i_only = -1, outside = true, sides = [0, 1], shrink = true) {
    for (side = sides, i = [0:5]) if (i_only < 0 || i == i_only) {
        s  = side == 0 ? 1 : -1;                   // into the box, along X
        xw = side == 0 ? 0 : CX;                   // the wall's inner face
        xe = side == 0 ? pcb_x0 + pcb_y - 93.15 : pcb_x0 + pcb_y - 1.68;   // terminal wire entry
        y  = lead_y[i];
        up = side == 1;
        xo = xw - s * (wall + 15.5 + 2.2 * (up ? 5 - i : i));
        for (w = [0:2]) {
            dy  = (w - 1) * 1.75;
            ye  = y + (w == 1 ? 1.75 : -1.75);     // green and white: the terminal's two ways
            out = [[xo, up ? CY + wall + 110 : -wall - 110, 8 + dy],
                   [xo, up ? CY + wall + 60 : -wall - 25, split_z + dy],
                   [xo, y + (up ? 8 : -8), split_z + dy],
                   [xo + s, y + (up ? 3 : -3), split_z + dy / 2],
                   [xw - s * (wall + 3), y + dy, split_z]];
            jaw = [for (x = [-wall - 1, 2.5, 4.5, 6.5, 8.5, jaw_len + 1])
                      [xw + s * x, y + dy, split_z + lead_bite / 2 *
                          (x == 2.5 || x == 6.5 ? 1 : x == 4.5 || x == 8.5 ? -1 : 0)]];
            inside = w == 0 ? [[xw + s * (jaw_len + 3), y + dy, split_z]]
                            : [[xw + s * (jaw_len + 5), y + dy * 0.6, split_z - 1.5],
                               [xe - s * 2, ye, pcb_top + 4], [xe + s * 3, ye, pcb_top + 4]];
            wire(concat(outside ? out : [], jaw, inside), 1.6, LEAD[w]);
        }
        if (shrink) color("#222") clip() translate([xw + s * (jaw_len + 3), y - 1.75, split_z])
            rotate([0, 90, 0]) cylinder(d = 2.5, h = 4, center = true);             // heat-shrink
    }
}

// The 24 drop wires: from each output and negative-bus screw into the channel
// beside the block. The right half's go up and out of the roof slot; the left
// half's go down the channel, through the divider, past the board and out of
// the floor slot.
module ghost_drop_wires() {
    for (side = [0, 1]) {
        s  = side == 0 ? -1 : 1;
        up = side == 1;
        ts = concat([for (i = [0:5]) [blk_cx + s * 36, blk_y1 - 52 - 12.6 * i]],
                    [for (r = [23, 34], k = [0:2]) [blk_cx + s * (12 + 10 * k), blk_y1 - r]]);
        for (j = [0:11]) {
            t  = ts[j];
            gx = up ? drop_up_x + (j % 4 - 1.5) * 3.5 : (dn_lo + dn_hi) / 2 + (j % 3 - 1) * 3.4;
            gz = up ? drop_z0 + 4.5 + floor(j / 4) * 3.5 : drop_z0 + 3 + floor(j / 3) * 3.4;
            zt = blk_z0 + 19 + (j >= 6 ? 2 : 0);
            wire([[t[0], t[1], zt - 2], [t[0], t[1], zt], [gx, t[1] + (up ? 4 : -4), gz],
                  [gx, up ? CY + wall + 70 : -wall - 70, gz]], 3.2, j < 6 ? "#b3261e" : "#1e1e1e");
            color("#c98a4b") translate([t[0], t[1], blk_z0 + 16]) cylinder(d = 7, h = 1);
        }
    }
}

// The controller's 5 V (E-1): a 14 AWG lead stacked on fuse R07's output
// screw, over the panel drop's ring, to J13+. R07 is the left column's bottom
// fuse, the one nearest J13. The return comes off a negative-bus screw the
// same way and runs down the left channel above the drops.
module ghost_tap_wiring() {
    j13p = [pcb_x0 + pcb_y - 39.04, pcb_y0 + pcb_x, pcb_top + 4];
    j13m = [pcb_x0 + pcb_y - 44.12, pcb_y0 + pcb_x, pcb_top + 4];
    r07  = [blk_cx - 36, blk_y1 - 52 - 12.6 * 5, blk_z0 + 21];
    wire([r07, [r07[0] - 3, r07[1] - 8, 26], [r07[0] - 2, blk_y0 - 6, 28], [64, div_y1 + 3, 31],
          [j13p[0] - 6, div_y0 + 1, 33], [j13p[0], j13p[1] + 1, j13p[2]], [j13p[0], j13p[1] - 3, j13p[2]]],
         2.6, "#b3261e");
    wire([[blk_cx - 12, blk_y1 - 23, blk_z0 + 21], [blk_cx - 40, blk_y1 - 18, blk_z0 + 23],
          [dn_lo + 3, blk_y1 - 18, 31], [dn_lo + 3, div_y1 + 14, 31], [34, div_y1 + 6, 31],
          [62, div_y1 + 2, 32], [j13m[0] - 4, div_y0 + 1, 33], [j13m[0], j13m[1] + 1, j13m[2]],
          [j13m[0], j13m[1] - 3, j13m[2]]], 2.6, "#1e1e1e");
}

// Cat5e: plug into the module, out through the opening, down the side of the
// box past the tie lug.
module ghost_eth() {
    c  = [eth_c[0], eth_c[1], eth_z];
    xl = CX + wall + 11;                           // the lead's run down the side, outside the tie lug
    zl = split_z - 8;
    color("#dde6ee") clip() translate([c[0], c[1] - 5.9, c[2] - 4.2]) cube([16, 11.8, 8.4]);
    color("#2f6fb5") clip() translate([c[0] + 16, c[1] - 4, c[2] - 3.5]) cube([6, 8, 7]);
    wire([[c[0] + 21, c[1], c[2]], [CX + wall + 5, c[1], c[2]], [xl - 2, c[1] + 3, c[2] - 3],
          [xl, c[1] + 5, zl + 8], [xl, c[1] + 2, zl], [xl, c[1] - 12, zl], [xl, -25, zl],
          [xl, -55, 12], [xl, -110, 5]], 5.8, "#2f6fb5");
    // cable tie: through the lug's slot and round the lead
    color("#161616") clip() translate([0, c[1] - 2.3, 0]) difference() {
        translate([CX + wall + 2.7, 0, zl - 6.8]) cube([xl + 4.2 - (CX + wall + 2.7), 4.6, 14.6]);
        translate([CX + wall + 4, -1, zl - 5.5]) cube([xl + 2.9 - (CX + wall + 4), 6.6, 12]);
    }
}

// Screws, bolts and nuts.
module ghost_hw(block = true) {
    color(STEEL) {
        for (p = door_holes) translate([p[0], p[1], 0]) {                 // #8 pan heads, washers
            cylinder(d = 10, h = 0.8);
            translate([0, 0, 0.8]) cylinder(d = 8.2, h = 2.6, $fn = 24);
        }
        for (p = blk_holes) translate([p[0], p[1], 0]) {                   // block bolts
            cylinder(d = 3.9, h = blk_z0 + 16 + 5.5, $fn = 16);
            if (block) {
                translate([0, 0, blk_z0 + 16]) cylinder(d = 9, h = 0.8);
                translate([0, 0, blk_z0 + 16.8]) cylinder(d = 7.9, h = 3.2, $fn = 6);
            }
        }
        for (y = [clamp_len / 2, CY - clamp_len / 2], s = [-1, 1])       // feed clamp screws
            translate([blk_cx + s * clamp_sx, y, split_z - 4]) cylinder(d = 7, h = 4, $fn = 24);
        for (h = pcb_holes) translate(concat(B(h[0], h[1]), pcb_top)) cylinder(d = 5.5, h = 2, $fn = 24);
    }
}

module ghost_bolt_heads() {                        // captive in the back of the floor
    color(STEEL) for (p = blk_holes) translate([p[0], p[1], -floor_t]) cylinder(d = 7 / cos(30), h = 2.8, $fn = 6);
}

module ghost_feeds_colour() {                      // - black, + red
    wire(minus_route(), feed_od, "#1a1a1a");
    color("#a8322d") translate([blk_cx, blk_y0 - lug_reach, feed_z]) rotate([90, 0, 0])
        cylinder(d = feed_od, h = blk_y0 - lug_reach + wall + 90);
    for (e = [[blk_y1 + lug_reach, 1, "#2a2a2a"], [blk_y0 - lug_reach, -1, "#7d1f1a"]])
        color(e[2]) translate([blk_cx, e[0] + (e[1] > 0 ? 0 : -shrink_len), feed_z]) rotate([-90, 0, 0])
            cylinder(d = feed_od + 1, h = shrink_len);
}

module unit_inside() {
    ghost_block(); ghost_feeds_colour(); ghost_drop_wires(); ghost_board();
    ghost_leads(); ghost_tap_wiring(); ghost_eth(); ghost_hw();
}

// The unit on its door. covers = false shows it with the lid and cover off.
module scene_unit(covers) {
    $block_cover = !covers;                        // seen only through the LED slot when closed
    upright() {
        ghost_door(-75, CX + 75, -175, CY + 170);
        color(PRINT) tub_solid();
        clamp_pair();
        unit_inside();
        if (covers) { color(LID_C) lid_solid(); color(COVER_C) cover_solid(); }
    }
    if (covers) {
        anchor("lid",     [CX * 0.78, blk_ym + 55, inner_h + top_t]);
        anchor("cover",   [CX * 0.8, pcb_y0 + 18, inner_h + top_t]);
        anchor("led",     [blk_cx, blk_y1 - (blk_led_from + blk_led_to) / 2 + 20, inner_h + top_t]);
        anchor("dip",     [(dip_lo[0] + dip_hi[0]) / 2, (dip_lo[1] + dip_hi[1]) / 2, inner_h + top_t]);
        anchor("leads",   [CX + wall + 21, lead_y[5] + 30, split_z]);
        anchor("eth",     [CX + wall + 7, eth_c[1] + 2, eth_z - 3]);
    } else {
        anchor("block",   [blk_cx + 32, blk_ym + 30, blk_z0 + blk_h]);
        anchor("fuses",   [blk_cx + 20, blk_y1 - 52 - 12.6 * 2, blk_z0 + 27]);
        anchor("lug_minus", [blk_cx, blk_y1 + lug_reach / 2, feed_z + 5]);
        anchor("lug_plus",  [blk_cx, blk_y0 - lug_reach / 2, feed_z + 5]);
        anchor("clamp_top", [blk_cx + clamp_sx + 4, CY - clamp_len / 2, split_z]);
        anchor("clamp_bot", [blk_cx + clamp_sx + 4, clamp_len / 2, split_z]);
        anchor("board",   [pcb_x0 + 70, pcb_y0 + 8, pcb_top]);
        anchor("devkit",  [pcb_x0 + 50, B(48.27, 50)[1], dk_z + 1.6]);
        anchor("usb",     [B(0, dk_usb_by)[0] + 3, B(48.27, 0)[1], dk_z + 3.2]);
        anchor("ethmod",  [eth_c[0] - 10, eth_c[1], dk_z + 1.6 + rj45_h]);
        anchor("tap",     [blk_cx - 36, blk_y1 - 52 - 12.6 * 5, blk_z0 + 21]);
        anchor("jaws",    [CX - jaw_len / 2, lead_y[3], split_z]);
        anchor("channel", [drop_up_x, blk_y0 + 95, drop_z0 + 12]);
        anchor("dip",     [B(0, (sw1_box[1] + sw1_box[3]) / 2)[0], B((sw1_box[0] + sw1_box[2]) / 2, 0)[1], pcb_top + 6.5]);
    }
    anchor("feed_minus", [blk_cx - feed_bend, CY + wall + 12 + feed_bend, feed_z]);
    anchor("feed_plus",  [blk_cx, -wall - 45, feed_z]);
    anchor("drops",      [drop_up_x - 5, CY + wall + 40, drop_z0 + 12]);
    anchor("drops_dn",   [(dn_lo + dn_hi) / 2, -wall - 45, drop_z0 + 12]);
    anchor("door",       [CX + 45, CY - 60, -floor_t]);
}

// A thin slice through one data lead (J10's), seen end on. step 1: the lead
// laid in the tub's groove, green and white in J10; 2: the cover coming down;
// 3: cover on, the lead pressed into a wave between the staggered ribs.
module scene_lead(step) {
    y0 = lead_y[2];
    $slab = [[-60, y0 - 0.9, -60], [140, 7, 160]];          // cut just in front of the green wire
    lift = step == 2 ? 7 : 0;
    ghost_door(-60, 80, y0 - 5, y0 + 20);
    color(PRINT) clip() tub_solid();
    if (step >= 2) translate([0, 0, lift]) color(COVER_C) clip() cover_solid();
    ghost_leads(i_only = 2, sides = [0], shrink = false);   // red is in front of the cut
    color("#1f6f43") clip() translate([pcb_x0, pcb_y0, standoff_h]) cube([pcb_y, pcb_x, pcb_t]);
    color("#2e8b57") clip() translate(concat(B(term_x[3] + 3.9, 93.15), pcb_top)) cube([7.7, 7.8, term_h]);
    anchor("tub_ribs",   [6.5, y0, split_z - lead_t / 2 + 0.2], false);
    anchor("cover_ribs", [8.5, y0, split_z + lead_t / 2 - 0.2 + lift], false);
    anchor("lead_in",    [3.5, y0, split_z + 0.4], false);
    anchor("mouth",      [-wall + 0.4, y0, split_z - 1.6], false);
    anchor("outside",    [-6.5, y0, split_z + 0.6], false);
    anchor("to_j10",     [jaw_len + 5, y0, split_z - 1.2], false);
    anchor("gusset",     [3, y0, split_z - lead_t / 2 - jaw_h - 3], false);
    anchor("tub",        [-wall / 2, y0, split_z - 9], false);
    anchor("cover",      [-wall / 2, y0, split_z + 7 + lift], false);
}

// Mounting. view "front": the empty tub on the door with its screws and the
// block bolts standing up, the block about to drop onto them. "back": the
// tub's back face, door removed. "bolt" and "screw": slices through a block
// bolt and a door screw.
module scene_mount(view) {
    if (view == "front") {
        upright() {
            ghost_door(-75, CX + 75, -175, CY + 170);
            color(PRINT) tub_solid();
            ghost_hw(block = false);
        }
        anchor("screw_top",  [door_holes[0][0], door_holes[0][1], 3.4]);
        anchor("screw_pcb",  [door_holes[5][0], door_holes[5][1], 3.4]);
        anchor("screw_bot",  [door_holes[7][0], door_holes[7][1], 3.4]);
        anchor("bolt",       [blk_holes[3][0], blk_holes[3][1], blk_z0 + 21]);
        anchor("seat",       [blk_cx + 20, blk_ym, blk_z0]);
        anchor("door",       [CX + 50, -45, -floor_t]);
    } else if (view == "back") {
        upright() { color(PRINT) tub_solid(); ghost_bolt_heads(); }
        anchor("bolt_head",  [blk_holes[1][0], blk_holes[1][1], -floor_t]);
        anchor("door_hole",  [door_holes[1][0], door_holes[1][1], -floor_t]);
        anchor("door_hole2", [door_holes[6][0], door_holes[6][1], -floor_t]);
        anchor("back",       [CX * 0.3, CY * 0.45, -floor_t]);
    } else {
        p = view == "bolt" ? blk_holes[2] : door_holes[3];
        $slab = [[p[0] - 30, p[1], -60], [60, 6, 120]];
        color(DOOR_C) clip() difference() {             // drilled for the screw
            translate([p[0] - 40, p[1] - 5, -floor_t - DOOR_T]) cube([80, 25, DOOR_T]);
            if (view == "screw") translate([p[0], p[1], -floor_t - 20]) cylinder(d = 4, h = 21, $fn = 16);
        }
        color(PRINT) clip() tub_solid();
        if (view == "bolt") {
            color("#2b2b2b") clip() difference() {
                translate([blk_cx - blk_w / 2, blk_y0, blk_z0]) cube([blk_w, blk_l, 16]);
                translate([p[0], p[1], 0]) cylinder(d = 4.4, h = 50, $fn = 16);
            }
            color(STEEL) clip() translate([p[0], p[1], 0]) {
                translate([0, 0, -floor_t]) cylinder(d = 7 / cos(30), h = 2.8, $fn = 6);
                cylinder(d = 3.9, h = blk_z0 + 16 + 5.5, $fn = 16);
                translate([0, 0, blk_z0 + 16]) cylinder(d = 9, h = 0.8);
                translate([0, 0, blk_z0 + 16.8]) cylinder(d = 7.9, h = 3.2, $fn = 6);
            }
        } else color(STEEL) clip() translate([p[0], p[1], 0]) {
            cylinder(d = 10, h = 0.8);
            translate([0, 0, 0.8]) cylinder(d = 8.2, h = 2.6, $fn = 24);
            translate([0, 0, -floor_t - 16]) cylinder(d = 4, h = floor_t + 16, $fn = 16);
            translate([0, 0, -floor_t - 18]) cylinder(d1 = 0.5, d2 = 4, h = 2, $fn = 16);
        }
        if (view == "bolt") {
            anchor("head",   [p[0] - 3, p[1], -floor_t + 1.4], false);
            anchor("floor",  [p[0] - 12, p[1], 1.5], false);
            anchor("block",  [p[0] - 14, p[1], blk_z0 + 10], false);
            anchor("nut",    [p[0] + 2, p[1], blk_z0 + 18.4], false);
            anchor("door",   [p[0] + 12, p[1], -floor_t - DOOR_T / 2], false);
        } else {
            anchor("head",   [p[0] + 2, p[1], 2.5], false);
            anchor("floor",  [p[0] - 12, p[1], -1.5], false);
            anchor("thread", [p[0] + 1, p[1], -floor_t - 9], false);
            anchor("door",   [p[0] - 14, p[1], -floor_t - DOOR_T / 2], false);
        }
    }
}

// ------------------------------------------------------------------- render --
PRINT = "#e6e1d6";      // colour for the renders; ignored by STL export

module to_bed() { translate([wall, wall, floor_t]) children(); }
module flip()   { rotate([180, 0, 0]) children(); }

module print_tub_upper() { to_bed() intersection() {
    tub_solid(); translate([-EX, y_split, -TRIM / 2]) cube([3 * EX, 2 * EY, TRIM]); } }
module print_tub_lower() { to_bed() intersection() {
    tub_solid(); translate([-EX, y_split - 2 * EY, -TRIM / 2]) cube([3 * EX, 2 * EY, TRIM]); } }
module print_lid()   { translate([wall, CY + wall, inner_h + top_t]) flip() lid_solid(); }
module print_cover() { translate([wall, y_split, inner_h + top_t]) flip() cover_solid(); }
module print_clamp() { translate([clamp_w / 2 - blk_cx, clamp_len, split_z]) flip() clamp_solid(); }

// Dimension line on the door face, for the door render.
module dim_x(x0, x1, y, label) {
    color("#222") translate([0, 0, -floor_t + 0.5]) {
        translate([x0, y - 0.6, 0]) cube([x1 - x0, 1.2, 1]);
        for (x = [x0, x1]) translate([x - 0.6, y - 5, 0]) cube([1.2, 10, 1]);
        translate([(x0 + x1) / 2, y - 12, 0]) linear_extrude(1)
            text(label, size = 8, halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
    }
}

if (part == "tub")            color(PRINT) to_bed() tub_solid();
else if (part == "tub_upper") color(PRINT) print_tub_upper();
else if (part == "tub_lower") color(PRINT) print_tub_lower();
else if (part == "lid")       color(PRINT) print_lid();
else if (part == "cover")     color(PRINT) print_cover();
else if (part == "clamp")     color(PRINT) print_clamp();
else if (part == "coupon")    color(PRINT) coupon();
else if (part == "template")  color(PRINT) template();
else if (part == "kit") {     // everything printed for one unit, as it sits on the bed
    color(PRINT) {
        print_tub_upper();
        translate([0, -EY + y_split - 20, 0]) print_tub_lower();
        translate([EX + 20, 0, 0]) print_lid();
        translate([EX + 20, -EY + y_split - 20, 0]) print_cover();
        for (i = [0:1]) translate([2 * EX + 40, 40 * i, 0]) print_clamp();
        translate([2 * EX + 40, 100, 0]) coupon();
        translate([2 * EX + 100, -120, 0]) template();
    }
}
else if (part == "open") {    // covers off: what you see with the door open
    color(PRINT) tub_solid(); clamp_pair(); ghosts();
}
else if (part == "exploded") {
    color(PRINT) tub_solid(); ghosts();
    translate([0, 0, 18]) clamp_pair();
    translate([0, 0, 70]) { color("#cfcac0", 0.85) lid_solid(); color("#d8d3c9", 0.85) cover_solid(); }
}
else if (part == "illus_closed")  scene_unit(true);
else if (part == "illus_open")    scene_unit(false);
else if (part == "illus_lead")    scene_lead(step);
else if (part == "illus_mount")   scene_mount(view);
else if (part == "door") {    // two units on one 16 in door, hinge on the left
    // Each box needs ~26 mm on its left for the - feed and ~20 mm on its right
    // for the rows 1-6 leads and the Cat5e, so the gaps are 30, 50 and 38 mm.
    door_w = 406.4;
    edge   = 30;                // hinge edge to the first box
    mid    = 50;                // between the boxes
    x0     = -wall - edge;
    color("#c8a97e") translate([x0, -wall - 140, -floor_t - 18]) cube([door_w, EY + 280, 18]);
    color("#555") for (y = [-wall - 60, EY - 80]) translate([x0 - 12, y, -floor_t - 18]) cube([12, 60, 18]);
    for (i = [0:1]) translate([i * (EX + mid), 0, 0]) { unit_closed(); ghost_feeds(tail = 45); ghost_drops(); }
    dim_x(x0, x0 + door_w, -wall - 110, "406 mm (16 in) door");
    for (i = [0:1]) dim_x(i * (EX + mid) - wall, i * (EX + mid) - wall + EX, -wall - 70, str(EX, " mm"));
}
else {
    unit_closed(); ghost_feeds(); ghost_drops();
}
