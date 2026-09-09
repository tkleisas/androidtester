// camera_mounts.scad — machine-vision mounts.
//   overhead_clamp — clamps the rear 2020 post, holds the overhead webcam
//                    CAM_POST_H (400 mm) above the deck centre
//   toolcam_bracket — toolhead camera on the gantry plate's rear M3 pattern
//
// Export: openscad -o overhead_clamp.stl -D 'PART="overhead_clamp"' camera_mounts.scad
include <00_config.scad>

PART = is_undef(_AT_PART) ? "preview" : _AT_PART;  // -D 'PART=...' or a render wrapper overrides

module overhead_clamp() {
    w = EXT + 16;        // wraps the post with two 8 mm cheeks
    t = 5;
    arm = 60;            // camera arm toward the deck centre
    difference() {
        union() {
            // C-clamp around the 2020 post
            cube([w, EXT + 2 * t, t]);                  // jaw bottom
            translate([0, 0, t]) cube([t, EXT + 2 * t, EXT]); // spine
            translate([0, 0, t + EXT]) cube([w, EXT + 2 * t, t]); // jaw top
            // camera arm off the top jaw
            translate([w, t, t + EXT]) cube([arm, EXT, t]);
        }
        // M5 clamp screw pulling the jaws onto the post slots
        translate([w - 6, t + EXT / 2, -0.1]) cylinder(d = M5_CLEAR, h = t + 0.2);
        // webcam plate holes: 2 x M3 on 25 mm spacing at the arm end
        for (sx = [-1, 1])
            translate([w + arm - 12 + sx * 12.5, t + EXT / 2, t + EXT - 0.1])
                cylinder(d = M3_CLEAR, h = t + 0.2);
    }
}

module toolcam_bracket() {
    w = 30;
    t = 5;
    drop = 35;           // camera sits below the plate, lens past the finger
    difference() {
        union() {
            cube([w, w, t]);                             // flange to the plate
            translate([0, w - t, -drop]) cube([w, t, drop + t]); // vertical leg
            translate([0, w - t - 15, -drop]) cube([w, 15, t]); // camera shelf
        }
        // flange holes matching the toolhead plate rear pattern (20 mm)
        for (sx = [-1, 1])
            translate([w / 2 + sx * 10, w / 2, -0.1])
                cylinder(d = M3_CLEAR, h = t + 0.2);
        // camera M3 holes in the shelf
        for (sx = [-1, 1])
            translate([w / 2 + sx * 10, w - t - 7.5, -drop - 0.1])
                cylinder(d = M3_CLEAR, h = t + 0.2);
    }
}

// -- preview / selector ---------------------------------------------------------
if (PART == "preview" || PART == "overhead_clamp")
    overhead_clamp();
if (PART == "preview")
    translate([110, 0, 45]) toolcam_bracket();
else if (PART == "toolcam_bracket")
    toolcam_bracket();
