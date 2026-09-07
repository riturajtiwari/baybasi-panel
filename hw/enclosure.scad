// Baybasi pixel wall — column controller enclosure, rev A
//
// A two-part printed box for the 100 x 95 mm controller board. Every external
// connection lands on the enclosure, not on the PCB: the twelve panel leads and
// the 5 V feed plug into sockets held in the walls, and short pigtails run from
// those sockets to the board's screw terminals. Pulling a cable loads the box,
// never the board, and a controller can be swapped without touching the twelve
// panel leads.
//
// The box splits horizontally at the connector centreline, so the JST-SM
// housings drop into half-pockets in the tub and the cover traps them. Nothing
// snaps, nothing is glued, and a housing cannot pull through because its wires
// leave through a slot narrower than the housing.
//
// PRINT THE COUPON FIRST.  Set part="coupon", print it, and check that a JST-SM
// housing sits in the pocket without slop and that an M3 insert seats. Four
// dimensions below are taken from catalogue drawings rather than from parts in
// hand; the coupon costs ten minutes and the full box costs eight hours.
//
//   openscad -D 'part="tub"'    -o tub.stl    enclosure.scad
//   openscad -D 'part="cover"'  -o cover.stl  enclosure.scad
//   openscad -D 'part="coupon"' -o coupon.stl enclosure.scad

part = "tub";           // [tub, cover, coupon, assembled]

/* [Measure these before printing the box] */
jst_w      = 9.6;       // JST-SM 3-pin housing, width across the three ways
jst_h      = 5.8;       // housing height
jst_len    = 13.0;      // housing length, mating face to wire exit
rj45_h     = 13.5;      // height of the RJ45 jack above the W5500 module's PCB
sock_h     = 8.5;       // height of the plug-in sockets (A1L/A1R, M1/M2)

/* [Board — do not change, taken from baybasi-ctrl.kicad_pcb] */
pcb_x      = 100;
pcb_y      = 95;
pcb_t      = 1.6;
pcb_holes  = [[4.4, 4.4], [95.6, 4.4], [4.4, 90.6], [95.6, 90.6]];
term_x     = [40.0, 49.2, 58.4, 67.6, 76.8, 86.0];  // J1..J6 and J7..J12 centres
eth_x      = 15.0;      // centre of the W5500's RJ45, in board x

/* [Box] */
wall       = 2.5;
floor_t    = 2.5;
top_t      = 2.5;
gap_n      = 22;        // north wall: clearance for the Ethernet plug
gap_s      = 20;        // south wall: clears the J7..J12 bodies by 6 mm
gap_w      = 18;        // west wall: power inlet and J13
gap_e      = 6;
inner_h    = 34;        // floor to ceiling; the RJ45 tops out near 30
standoff_h = 5;         // PCB above the floor, clears the terminal-block pins
split_z    = 12;        // tub/cover joint, and the socket centreline
fillet     = 3;

/* [Sockets] */
sock_pitch = 12;        // JST-SM sockets on the north and south walls
eth_w      = 18;        // Ethernet opening, wide enough to reach the plug latch
eth_hi     = 16;
pwr_d      = 8;         // panel-mount barrel jack; see notes for XT30 or GX12

/* [Fasteners] */
m3_free    = 3.4;       // clearance for an M3 screw
m3_insert  = 4.0;       // heat-set insert, brass, M3 x 4 mm
boss_d     = 8;

$fn = 48;
TRIM = 200;             // oversized solid for splitting the box at split_z

// ---------------------------------------------------------------- geometry --
CX = gap_w + pcb_x + gap_e;      // cavity, x
CY = gap_n + pcb_y + gap_s;      // cavity, y
CZ = inner_h;
EX = CX + 2 * wall;
EY = CY + 2 * wall;

function board(bx, by) = [gap_w + bx, gap_n + by];

// Socket x positions, centred on the terminal block group they serve.
term_mid  = gap_w + (term_x[0] + term_x[5]) / 2;
sock_x    = [for (i = [0:5]) term_mid + (i - 2.5) * sock_pitch];
corner_xy = [[6, 6], [CX - 6, 6], [6, CY - 6], [CX - 6, CY - 6]];

// ------------------------------------------------------------------ pieces --
// Rounded outer shell, drawn from the cavity's origin.
module shell(z0, z1) {
    translate([-wall, -wall, z0])
        hull() for (x = [fillet, EX - fillet], y = [fillet, EY - fillet])
            translate([x, y, 0]) cylinder(r = fillet, h = z1 - z0);
}

module cavity(z0, z1) {
    translate([0, 0, z0]) cube([CX, CY, z1 - z0]);
}

// A JST-SM socket, cut into a wall. Placed at the wall's inner face with the
// housing going outward along -y; rotate for the other walls.
//   - a through-slot the size of the housing, so the mating half can engage
//   - a pocket the length of the housing
//   - a rear wall pierced only by a wire slot, which is what stops the housing
//     being pulled out through the wall
back = 3;               // rear wall of each pocket; the housing butts on this

module jst_cut() {
    translate([0, (jst_len - wall - 2) / 2, 0])              // pocket
        cube([jst_w + 0.3, jst_len + wall + 2, jst_h + 0.3], center = true);
    translate([0, jst_len + back - 1, 0])                    // wire exit
        cube([jst_w - 3.5, back * 2 + 2, jst_h + 0.3], center = true);
}

module jst_boss() {
    translate([0, (jst_len + back - wall) / 2, 0])
        cube([jst_w + 5, jst_len + back + wall, jst_h + 5], center = true);
}

// Bosses and columns ---------------------------------------------------------
module pcb_bosses(bore) {
    for (h = pcb_holes) {
        p = board(h[0], h[1]);
        translate([p[0], p[1], 0]) difference() {
            cylinder(d = boss_d, h = standoff_h);
            translate([0, 0, -1]) cylinder(d = bore, h = standoff_h + 2);
        }
    }
}

module screw_columns(z0, z1, bore) {
    for (c = corner_xy) translate([c[0], c[1], z0]) difference() {
        cylinder(d = boss_d + 2, h = z1 - z0);
        translate([0, 0, -1]) cylinder(d = bore, h = z1 - z0 + 2);
    }
}

// Openings -------------------------------------------------------------------
module wall_openings() {
    // twelve panel sockets: six north, six south
    for (x = sock_x) {
        translate([x, 0, split_z]) jst_cut();
        translate([x, CY, split_z]) rotate([0, 0, 180]) jst_cut();
    }
    // Ethernet: the lead plugs straight into the module through this opening.
    // No coupler — two RJ45 plugs nose to nose need 40 mm and there is 22.
    translate([board(eth_x, 0)[0], -wall - 1, standoff_h + pcb_t + sock_h + rj45_h / 2])
        cube([eth_w, wall + 2, eth_hi], center = true);
    // 5 V inlet on the west wall, in line with J13
    translate([-wall - 1, board(0, 41.6)[1], split_z + 8])
        rotate([0, 90, 0]) cylinder(d = pwr_d, h = wall + 2);
    // vents, east wall
    for (i = [0:5]) translate([CX - 1, CY / 2 - 30 + i * 12, split_z + 12])
        cube([wall + 2, 4, 14], center = true);
}

module socket_bosses() {
    for (x = sock_x) {
        translate([x, 0, split_z]) jst_boss();
        translate([x, CY, split_z]) rotate([0, 0, 180]) jst_boss();
    }
}

// A printed bridge outside the Ethernet opening. Zip-tie the lead to it and the
// box takes the strain instead of the module's socket pins.
module cable_clamp() {
    p = board(eth_x, 0)[0];
    difference() {
        translate([p - 13, -wall - 10, -floor_t]) cube([26, 10 + wall, floor_t + 6]);
        for (dx = [-7, 7]) translate([p + dx, -wall - 5, -floor_t - 1])
            cylinder(d = 4, h = floor_t + 8);
    }
}

// ------------------------------------------------------------------ the tub --
module tub() {
    difference() {
        union() {
            difference() {
                shell(-floor_t, split_z);
                cavity(0, split_z + 1);
            }
            socket_bosses();
            pcb_bosses(m3_insert);
            screw_columns(0, split_z, m3_insert);
            cable_clamp();
        }
        wall_openings();
        // keep the tub's half of every pocket open at the top
        translate([-EX, -EY, split_z]) cube([3 * EX, 3 * EY, TRIM]);
    }
}

// ---------------------------------------------------------------- the cover --
module cover() {
    difference() {
        union() {
            difference() {
                shell(split_z, inner_h + top_t);
                cavity(split_z - 1, inner_h);
            }
            socket_bosses();
            screw_columns(split_z, inner_h, m3_free);
        }
        wall_openings();
        translate([-EX, -EY, split_z - TRIM]) cube([3 * EX, 3 * EY, TRIM]);
        // vents in the roof
        for (i = [0:4]) translate([CX / 2 - 24 + i * 12, CY / 2, inner_h + top_t / 2])
            cube([4, 40, top_t + 2], center = true);
    }
}

// --------------------------------------------------------------- the coupon --
// One socket pocket, one insert boss, and a strip of wall. Print this, fit a
// real JST-SM housing and a real M3 insert, and adjust jst_w / jst_h / jst_len
// / m3_insert above before committing to the box.
module coupon() {
    difference() {
        union() {
            translate([-6, -wall, -split_z]) cube([sock_pitch * 2 + 12, wall, split_z * 2]);
            translate([sock_pitch / 2, 0, 0]) {
                translate([-sock_pitch / 2, 0, 0]) jst_boss();
                translate([sock_pitch / 2, 0, 0]) jst_boss();
            }
            translate([sock_pitch * 2 + 2, 6, -split_z])
                cylinder(d = boss_d, h = standoff_h);
        }
        jst_cut();
        translate([sock_pitch, 0, 0]) jst_cut();
        translate([sock_pitch * 2 + 2, 6, -split_z - 1])
            cylinder(d = m3_insert, h = standoff_h + 2);
    }
}

// ------------------------------------------------------------------- render --
module pcb_ghost() {
    color("green", 0.35) translate([gap_w, gap_n, standoff_h]) cube([pcb_x, pcb_y, pcb_t]);
}

if (part == "tub")           tub();
else if (part == "cover")    cover();
else if (part == "coupon")   coupon();
else {
    tub();
    pcb_ghost();
    color("silver", 0.30) cover();
}
