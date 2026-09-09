// device_nest.scad — adjustable fixture holding the device under test.
// Phones through ~11" tablets (up to DEVICE_MAX_W x DEVICE_MAX_D). Two fixed
// corner stops reference the device; two sliding clamps close against the
// other edges. Everything is NEST_STOP_H (8 mm) tall or shorter — below the
// screen, out of the overhead camera's view of the glass, and clear of the
// NEST_CLEAR (40 mm) ArUco marker zones at the deck corners.
//
// Parts (PART selector):
//   corner_stop — fixed L reference stop, M4 bolts to the deck plate
//   side_clamp  — sliding clamp: 30 mm slot + M5 thumb-screw tab
//
// Export: openscad -o corner_stop.stl -D 'PART="corner_stop"' device_nest.scad
include <00_config.scad>

PART = is_undef(_AT_PART) ? "preview" : _AT_PART;  // -D 'PART=...' or a render wrapper overrides

module corner_stop() {
    arm = 35;
    t = NEST_STOP_H;
    w = 12;              // arm width
    difference() {
        union() {
            cube([arm, w, t]);
            cube([w, arm, t]);
        }
        // M4 bolt holes at the arm ends (deck plate M4 grid)
        translate([arm - 8, w / 2, -0.1]) cylinder(d = M4_CLEAR, h = t + 0.2);
        translate([w / 2, arm - 8, -0.1]) cylinder(d = M4_CLEAR, h = t + 0.2);
        // 45° relief at the inner vertex (w,w) so the device's rounded
        // corner / case lip doesn't ride on the reference corner
        translate([w, w, -0.1]) rotate([0, 0, 45])
            cube([5, 5, t + 0.2], center = true);
    }
}

module side_clamp() {
    l = 60;
    w = 14;
    t = NEST_STOP_H;
    slot_l = 30;
    difference() {
        union() {
            cube([l, w, t]);
            // thumb-screw tab standing off the back
            translate([l - 10, w, 0]) cube([10, 8, t]);
        }
        // M5 clamp slot (bolt + T-nut into the deck plate)
        hull()
            for (x = [10, 10 + slot_l])
                translate([x, w / 2, -0.1]) cylinder(d = M5_CLEAR, h = t + 0.2);
        // M5 clearance in the thumb tab
        translate([l - 5, w + 4, -0.1]) cylinder(d = M5_CLEAR, h = t + 0.2);
        // rubber-pad recess on the device contact face (10 x 10 x 1.5)
        translate([-0.1, w / 2 - 5, t - 4]) cube([1.5 + 0.1, 10, 4]);
    }
}

// -- preview / selector ---------------------------------------------------------
if (PART == "preview" || PART == "corner_stop")
    corner_stop();
if (PART == "preview")
    translate([50, 0, 0]) side_clamp();
else if (PART == "side_clamp")
    side_clamp();
