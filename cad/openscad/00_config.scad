// 00_config.scad — shared dimensions for the AndroidTester machine, in mm.
//
// These constants are the single source for every part in cad/openscad/.
// They are cross-checked by tests/test_design_package.py against
// androidtester/config.py (deck size, clearance planes) and
// firmware/klipper/androidtester.cfg (position_max) — change them together.

// -- deck and travels -------------------------------------------------------
// Deck == reachable XY (cfg position_max == config.py deck defaults).
DECK_W   = 400;          // deck X, config.py deck_width_mm, stepper_x position_max
DECK_D   = 300;          // deck Y, config.py deck_height_mm, stepper_y position_max
X_TRAVEL = 400;          // == DECK_W
Y_TRAVEL = 300;          // == DECK_D
Z_TRAVEL = 60;           // tool-Z elevator travel (manual_stepper tool_z)
TRAVEL_Z = 40;           // clearance plane, config.py travel_z_mm
TOUCH_Z  = 5;            // finger-tip contact plane, config.py touch_z_mm

// -- linear rails -------------------------------------------------------------
// X rail: must span the full X travel plus the carriage plus end margins:
//   X_TRAVEL (400) + X_CARRIAGE_LEN (45) + 2*END_MARGIN (10) = 465 mm min
//   -> RAIL_X_LEN = 500 (next stock MGN12 length, 35 mm of setup slack).
// Y rails (x2, carry the gantry beam):
//   Y_TRAVEL (300) + X_CARRIAGE_LEN (45) + 2*END_MARGIN (10) = 365 mm min
//   -> RAIL_Y_LEN = 400.
// Z rail (tool elevator, MGN9):
//   Z_TRAVEL (60) + Z_CARRIAGE_LEN (40) + 2*END_MARGIN (10) = 120 mm min
//   -> RAIL_Z_LEN = 150.
RAIL_X_LEN = 500;
RAIL_Y_LEN = 400;
RAIL_Z_LEN = 150;
X_CARRIAGE_LEN = 45;     // MGN12H block, 27 x 45.4 mm (nominal — verify rail vendor)
Z_CARRIAGE_LEN = 40;     // MGN9H block, 20 x 38.9 mm (nominal — verify rail vendor)
END_MARGIN   = 10;       // endstop trigger + belt/idler clearance at each rail end
RAIL12_W = 12;           // MGN12 rail width / height
RAIL12_H = 8;
RAIL9_W  = 9;            // MGN9 rail width / height
RAIL9_H  = 6.5;

// -- frame --------------------------------------------------------------------
EXT = 20;                // 2020 aluminium extrusion (6 mm slot)
FRAME_W = DECK_W + 100;  // 500 — gantry beam carries the full X rail (500)
FRAME_D = DECK_D + 100;  // 400 — side beams carry the full Y rails (400)
POST_H  = 200;           // gantry posts above the base frame
CAM_POST_H = 400;        // overhead camera post above the deck

// -- motors / motion hardware ---------------------------------------------------
NEMA_W   = 42.3;         // NEMA17 face
NEMA_HOLE_SP = 31;       // NEMA17 M3 hole spacing
NEMA_BORE  = 22.2;       // NEMA17 pilot bore (clearance)
PULLEY_D = 12.2;         // GT2 20T pulley OD (2 mm pitch x 20 T = 40 mm/rev)
IDLER_D  = 12.2;         // GT2 20T idler OD, 5 mm bore
BELT_W   = 6;            // GT2 belt width
LEAD_D   = 8;            // T8 lead screw (2 mm pitch x 4 starts = 8 mm/rev)

// -- servos (SG90 / MG90S class) -------------------------------------------------
SERVO_W   = 23;          // body across tabs axis
SERVO_D   = 12.5;        // body depth
SERVO_H   = 23;          // body height below the mounting tabs
SERVO_TAB_W = 32.5;      // across the mounting tabs
SERVO_SHAFT_D = 5;       // output shaft / horn boss clearance
SERVO_SHAFT_OFF = 6;     // shaft centre from body end wall

// -- finger tool -----------------------------------------------------------------
FINGER_TIP_D  = 8;       // conductive tip diameter
FINGER_SHAFT_D = 6;      // plunger shaft
SPRING_D  = 8.5;         // compression-spring pocket (Ø8 spring, k ≈ 0.5 N/mm)
FINGER_STROKE = 15;      // spring working stroke (3–12 mm compression -> 1.5–6 N)

// -- fasteners ---------------------------------------------------------------------
M3_CLEAR = 3.2;
M4_CLEAR = 4.2;
M5_CLEAR = 5.3;
M3_HEAD  = 6.0;          // M3 button-head clearance

// -- device nest ---------------------------------------------------------------------
DEVICE_MAX_W = 280;      // phones through ~11" tablets (250 x 170 + case)
DEVICE_MAX_D = 200;
NEST_STOP_H  = 8;        // stop height: below screen, clear of ArUco markers
NEST_CLEAR   = 40;       // keep-out at each deck corner (ArUco marker zone)

$fn = 48;
