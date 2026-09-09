// button_plunger.scad — nest-mounted servo plunger for recessed side buttons
// (power / volume). The servo body bolts to a slotted base on the deck plate;
// its horn carries a Ø6 push pin riding in a guide bore, aligned with the
// device edge. Two of these live on the nest (plunger_0 / plunger_1).
//
// Parts (PART selector):
//   plunger_base — servo cradle + deck slots (M4, 15 mm edge-distance travel)
//   plunger_pin  — push pin with horn hub and return-spring groove
//
// Export: openscad -o plunger_base.stl -D 'PART="plunger_base"' button_plunger.scad
include <00_config.scad>

PART = is_undef(_AT_PART) ? "preview" : _AT_PART;  // -D 'PART=...' or a render wrapper overrides

module plunger_base() {
    base_w = 45;
    base_d = 24;
    t = 5;
    cradle_h = 20;
    gap = base_d - 2 * t;   // 14 mm = SERVO_D (12.5) + running clearance
    difference() {
        union() {
            cube([base_w, base_d, t]);
            // cradle walls: servo body drops between them, tabs rest on top
            for (sy = [0, base_d - t])
                translate([8, sy, t]) cube([SERVO_TAB_W + 4, t, cradle_h]);
        }
        // servo well between the walls, open at the top (tabs sit on the walls)
        translate([8 + 2, t - 0.1, t + 4])
            cube([SERVO_W + 0.4, gap + 0.2, cradle_h]);
        // pin guide bore Ø6.2 through both walls at horn height
        translate([8 - 0.1, base_d / 2, t + 12])
            rotate([0, 90, 0]) cylinder(d = 6.2, h = SERVO_TAB_W + 4.2);
        // M4 deck slots, 10 mm of edge-distance adjustment
        for (x = [12, base_w - 12])
            hull()
                for (dy = [-5, 5])
                    translate([x, base_d / 2 + dy, -0.1])
                        cylinder(d = M4_CLEAR, h = t + 0.2);
    }
}

module plunger_pin() {
    pin_l = 30;
    difference() {
        union() {
            cylinder(d = 6, h = pin_l);                       // push pin
            translate([0, 0, pin_l - 8]) cylinder(d = 12, h = 8); // horn hub
        }
        // horn boss bore + M3 screw
        translate([0, 0, pin_l - 8.1]) cylinder(d = SERVO_SHAFT_D, h = 8.2);
        // return-spring groove (Ø1 wire, 2 mm deep, 6 mm from the tip)
        translate([0, 0, 6]) rotate_extrude()
            translate([2, 0, 0]) square([2, 1.5]);
    }
}

// -- preview / selector ---------------------------------------------------------
if (PART == "preview" || PART == "plunger_base")
    plunger_base();
if (PART == "preview")
    translate([55, 15, 0]) plunger_pin();
else if (PART == "plunger_pin")
    plunger_pin();
