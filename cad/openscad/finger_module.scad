// finger_module.scad — the touch tool: a spring-loaded plunger with a
// conductive tip, carried on a servo-deployed swing arm (deploy = vertical
// working position, stow = swung clear for nest access).
//
// Tap force comes from the spring, not the Z drive: the tool-Z descends to
// TOUCH_Z with the tip already on the glass, compressing the spring 3–12 mm
// for 1.5–6 N (see docs/01-mechanical.md).
//
// Parts (PART selector):
//   finger_body — plunger housing: spring pocket, shaft guide, tip socket
//   deploy_arm  — swings the body on the finger_deploy servo (MG90S)
//
// Export: openscad -o finger_body.stl -D 'PART="finger_body"' finger_module.scad
include <00_config.scad>

PART = is_undef(_AT_PART) ? "preview" : _AT_PART;  // -D 'PART=...' or a render wrapper overrides

BODY_W = 24;
BODY_D = 16;
BODY_H = 40;             // spring pocket + guide + tip socket stack

module finger_body() {
    mount_h = 8;         // top mounting flange height
    difference() {
        union() {
            cube([BODY_W, BODY_D, BODY_H - mount_h]);
            translate([-4, 0, BODY_H - mount_h]) cube([BODY_W + 8, BODY_D, mount_h]);
        }
        // spring pocket open at the flange top: Ø8.5 (Ø8 spring, k ≈ 0.5 N/mm);
        // the toolhead plate above retains the spring once bolted down
        translate([BODY_W / 2, BODY_D / 2, BODY_H - mount_h - 25])
            cylinder(d = SPRING_D, h = 25 + mount_h + 0.1);
        // shaft guide Ø6.2 through the rest of the body
        translate([BODY_W / 2, BODY_D / 2, -0.1])
            cylinder(d = FINGER_SHAFT_D + 0.2, h = BODY_H);
        // tip socket: conductive tip Ø8 shank, 8 mm deep, from the bottom
        translate([BODY_W / 2, BODY_D / 2, -0.1])
            cylinder(d = FINGER_TIP_D + 0.1, h = 8);
        // M3 grub screw into the tip shank, from the +Y face
        translate([BODY_W / 2, -0.1, 4])
            rotate([-90, 0, 0]) cylinder(d = M3_CLEAR, h = BODY_D / 2 + 0.2);
        // mount holes matching the toolhead plate finger pattern (24 mm)
        for (sx = [-1, 1])
            translate([BODY_W / 2 + sx * 12, BODY_D / 2, BODY_H - mount_h - 0.1])
                cylinder(d = M3_CLEAR, h = mount_h + 0.2);
    }
}

// Servo swing arm: clamps on the finger_deploy servo horn boss, carries the
// finger body at its end. 90° swing = deploy (down) / stow (flat).
module deploy_arm() {
    arm_l = 34;          // shaft centre to body centre
    h = 6;
    difference() {
        union() {
            hull() {
                cylinder(d = 14, h = h);                       // hub
                // end pad covers the finger body's 24 mm M3 pattern
                translate([arm_l, 0, 0]) cube([26, 18, h], center = true);
            }
            cylinder(d = 10, h = h + 3);                       // horn boss
        }
        // horn boss bore + M3 horn screw
        translate([0, 0, -0.1]) cylinder(d = SERVO_SHAFT_D, h = h + 3.2);
        translate([0, 0, h + 1]) cylinder(d = M3_CLEAR, h = 2.2);
        // finger body bolts: 2 x M3 on the 24 mm pattern
        for (sx = [-1, 1])
            translate([arm_l + sx * 12, 0, -0.1])
                cylinder(d = M3_CLEAR, h = h + 0.2);
    }
}

// -- preview / selector ---------------------------------------------------------
if (PART == "preview" || PART == "finger_body")
    finger_body();
if (PART == "preview")
    translate([45, 8, 0]) rotate([0, 0, 90]) deploy_arm();
else if (PART == "deploy_arm")
    deploy_arm();
