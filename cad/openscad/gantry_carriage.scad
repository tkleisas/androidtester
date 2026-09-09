// gantry_carriage.scad — the CoreXY toolhead: plate on the X-rail carriage,
// GT2 belt terminations, and the mount points for the finger module and the
// toolhead camera bracket.
//
// Parts (PART selector):
//   toolhead_plate — main plate, bolts to the MGN12H block (M3, 20 x 20)
//   belt_clamp     — toothed wedge; two per plate trap the folded belt ends
//
// Export: openscad -o toolhead_plate.stl -D 'PART="toolhead_plate"' gantry_carriage.scad
include <00_config.scad>

PART = is_undef(_AT_PART) ? "preview" : _AT_PART;  // -D 'PART=...' or a render wrapper overrides

T = 6;                   // plate thickness
PLATE_W = 100;           // along X (rail direction)
PLATE_D = 60;            // along Y

module toolhead_plate() {
    difference() {
        cube([PLATE_W, PLATE_D, T]);
        // MGN12H block pattern (M3, 20 x 20 mm nominal — verify vendor block)
        for (sx = [-1, 1], sy = [-1, 1])
            translate([PLATE_W / 2 + sx * 10, PLATE_D / 2 + sy * 10, -0.1])
                cylinder(d = M3_CLEAR, h = T + 0.2);
        // belt slots: the 6 mm GT2 ends fold up through and are trapped by
        // belt_clamp wedges; one pair near each end of the plate
        for (x = [12, PLATE_W - 12 - 2 * (BELT_W + 3)])
            for (i = [0:1])
                translate([x + i * (BELT_W + 3), PLATE_D / 2 - 8, -0.1])
                    cube([BELT_W, 16, T + 0.2]);
        // belt_clamp screw holes: one M3 pair per slot pair, outside the slots
        for (x = [12 + 7.5, PLATE_W - 12 - 7.5])   // centre of each slot pair
            for (sy = [-1, 1])
                translate([x, PLATE_D / 2 + sy * 14, -0.1])
                    cylinder(d = M3_CLEAR, h = T + 0.2);
        // finger module mount: 2 x M3 on a 24 mm spacing, front centre
        for (sx = [-1, 1])
            translate([PLATE_W / 2 + sx * 12, 12, -0.1])
                cylinder(d = M3_CLEAR, h = T + 0.2);
        // toolcam bracket mount: 2 x M3 on a 20 mm spacing, rear centre
        for (sx = [-1, 1])
            translate([PLATE_W / 2 + sx * 10, PLATE_D - 12, -0.1])
                cylinder(d = M3_CLEAR, h = T + 0.2);
        // cable pass-through
        translate([PLATE_W / 2 - 7, PLATE_D / 2 - 6, -0.1])
            cube([14, 12, T + 0.2]);
    }
}

// Wedge that presses the folded belt into its slot pair; GT2 tooth ribs on
// the contact face, two M3 clamp screws on the plate holes (±14 mm) above.
module belt_clamp() {
    w = 2 * (BELT_W + 3) - 1;   // 17 mm, spans both slots of one pair
    d = 36;                     // reaches the screw holes 14 mm past the slots
    h = 8;
    difference() {
        union() {
            cube([w, d, h]);
            // tooth ribs gripping the belt back, protruding 1 mm below the
            // contact face, over the slot span only
            for (y = [11:2:25])
                translate([0, y, -1]) cube([w, 1, 3]);
        }
        for (y = [4, d - 4])
            translate([w / 2, y, -0.1]) cylinder(d = M3_CLEAR, h = h + 0.2);
    }
}

// -- preview / selector ---------------------------------------------------------
if (PART == "preview" || PART == "toolhead_plate")
    toolhead_plate();
if (PART == "preview")
    translate([20, PLATE_D + 15, 0]) belt_clamp();
else if (PART == "belt_clamp")
    belt_clamp();
