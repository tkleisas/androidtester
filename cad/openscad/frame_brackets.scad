// frame_brackets.scad — frame joinery and motion hardware mounts.
//
// Parts (PART selector):
//   corner_bracket — 3-way printed corner for the 2020 base frame
//   motor_plate    — NEMA17 plate, bolts to a 2020 face (CoreXY A/B motors)
//   idler_mount    — GT2 20T idler post plate for the belt return corners
//
// Export: openscad -o corner_bracket.stl -D 'PART="corner_bracket"' frame_brackets.scad
include <00_config.scad>

PART = is_undef(_AT_PART) ? "preview" : _AT_PART;  // -D 'PART=...' or a render wrapper overrides

T = 5;                   // bracket wall thickness

// 3-way corner: sits on the base-frame corner, the gantry post drops into the
// walled socket. M5 holes hit the extrusion end taps / T-nuts.
module corner_bracket() {
    arm = 2 * EXT;       // 40 mm arms
    wall = 4;
    difference() {
        union() {
            cube([arm, arm, T]);                       // base plate under the corner
            translate([0, 0, T]) cube([arm, EXT, EXT]); // X arm wraps the extrusion
            translate([0, 0, T]) cube([EXT, arm, EXT]); // Y arm
            // walled post socket, 2020 + 0.6 mm clearance inside
            translate([-wall, -wall, T + EXT])
                cube([EXT + 2 * wall, EXT + 2 * wall, EXT]);
        }
        // post pocket
        translate([-0.3, -0.3, T + EXT - 0.1])
            cube([EXT + 0.6, EXT + 0.6, EXT + 0.2]);
        // M5 through-holes into the extrusion end taps, 2 per arm
        for (x = [EXT / 2, 3 * EXT / 2])
            translate([x, EXT / 2, -0.1]) cylinder(d = M5_CLEAR, h = T + 0.2);
        for (y = [EXT / 2, 3 * EXT / 2])
            translate([EXT / 2, y, -0.1]) cylinder(d = M5_CLEAR, h = T + 0.2);
        // M5 clamp holes through the socket walls into the post T-slots
        translate([EXT / 2, EXT / 2, T + EXT + EXT / 2]) {
            rotate([0, 90, 0]) cylinder(d = M5_CLEAR, h = EXT + 2 * wall + 0.4, center = true);
            rotate([90, 0, 0]) cylinder(d = M5_CLEAR, h = EXT + 2 * wall + 0.4, center = true);
        }
    }
}

// NEMA17 against a 2020 face: motor on standoffs, M4 slot holes for the
// extrusion T-nuts so belt tension is adjustable before torquing down.
module motor_plate() {
    w = NEMA_W + 10;     // plate wider than the motor
    h = NEMA_W + 10;
    difference() {
        cube([w, h, T]);
        // NEMA17 bolt pattern + pilot bore
        translate([w / 2, h / 2, -0.1]) {
            cylinder(d = NEMA_BORE, h = T + 0.2);
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * NEMA_HOLE_SP / 2, sy * NEMA_HOLE_SP / 2, 0])
                    cylinder(d = M3_CLEAR, h = T + 0.2);
        }
        // M4 slots into the 2020 T-nuts (10 mm of tension travel), clear of
        // the pilot bore (Ø22.2 centred) and the NEMA hole pattern
        for (y = [8, h - 8])
            hull() {
                translate([w / 2 - 5, y, -0.1]) cylinder(d = M4_CLEAR, h = T + 0.2);
                translate([w / 2 + 5, y, -0.1]) cylinder(d = M4_CLEAR, h = T + 0.2);
            }
    }
}

// GT2 idler on an M5 shoulder bolt; slotted like the motor plate.
module idler_mount() {
    w = 30;
    h = 40;
    difference() {
        union() {
            cube([w, h, T]);
            translate([w / 2, 3 * h / 4, T]) cylinder(d = 14, h = IDLER_D + 2); // boss
        }
        // M5 idler bore through the boss
        translate([w / 2, 3 * h / 4, -0.1]) cylinder(d = M5_CLEAR, h = T + IDLER_D + 3);
        // M4 slots for the 2020 T-nuts, below the boss (clear of Ø14 at y=30)
        for (y = [6, 16])
            hull() {
                translate([w / 2 - 4, y, -0.1]) cylinder(d = M4_CLEAR, h = T + 0.2);
                translate([w / 2 + 4, y, -0.1]) cylinder(d = M4_CLEAR, h = T + 0.2);
            }
    }
}

// -- preview / selector ---------------------------------------------------------
if (PART == "preview" || PART == "corner_bracket")
    corner_bracket();
if (PART == "preview")
    translate([70, 0, 0]) motor_plate();
else if (PART == "motor_plate")
    motor_plate();
if (PART == "preview")
    translate([140, 0, 0]) idler_mount();
else if (PART == "idler_mount")
    idler_mount();
