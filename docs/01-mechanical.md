# 01 — Mechanical design

The machine is a CoreXY gantry over a **400 × 300 mm deck**, built from 2020
extrusion, MGN linear rails, and printed parts (`cad/openscad/`, all
parametric — every dimension lives in `00_config.scad`). A tool-Z elevator
raises/lowers the tools; a servo-deployed conductive finger does touch input;
two servo plungers in the nest press side buttons.

## Frame

Base frame 500 × 400 mm (2020 extrusion, printed 3-way `corner_bracket`s),
four 200 mm posts, two 400 mm side beams carrying the Y rails, one 500 mm
gantry beam carrying the X rail, one 400 mm camera post at the rear. The deck
plate (400 × 300 × 4 mm aluminium) bolts to the base frame with an M4 hole
grid for the nest hardware.

Cut plan (2020, in mm): 2×500 + 2×400 base, 4×200 posts, 2×400 side beams,
1×500 gantry beam, 1×400 camera post → **4.3 m total → buy 5× 1 m** (0.7 m
spare for jigs and mistakes).

## Motion layout

- **X/Y: CoreXY.** Two NEMA17s with GT2 20T pulleys (2.0 mm pitch × 20 teeth
  = **40.0 mm/rev** `rotation_distance`), belt routed around 6 idlers, both
  belt ends terminate in `belt_clamp` wedges on the `toolhead_plate`. X rides
  a single MGN12H rail on the gantry beam; the beam ends ride two MGN12H Y
  rails on the side beams.
- **Tool-Z: elevator.** NEMA17 + T8 lead screw (2 mm pitch × 4 starts =
  **8 mm/rev**), 5→8 mm coupler, MGN9H rail (150 mm) guiding the tool lift.
  Driven as a Klipper `manual_stepper` — no G-code path can move Z; only the
  macro contract touches it. Homes **up** against a microswitch at the top of
  travel, away from the deck.

### Rail lengths (the arithmetic)

Rail ≥ travel + carriage length + 2 × end margin (10 mm: endstop trigger +
belt/idler clearance at each end). Same numbers in `00_config.scad`, enforced
by `tests/test_design_package.py`:

| Axis | Travel | Carriage | Margins | Min rail | Stock rail |
|------|--------|----------|---------|----------|------------|
| X    | 400    | 45 (MGN12H) | 2×10 | **465** | **500** |
| Y    | 300    | 45 (MGN12H) | 2×10 | **365** | **400** (×2) |
| Z    | 60     | 40 (MGN9H)  | 2×10 | **120** | **150** |

Travels equal the deck size (`position_max` in the cfg == `deck_width_mm` /
`deck_height_mm` in `androidtester/config.py`), so the finger reaches every
deck point including the ArUco corner markers.

## Tools

- **Finger** (`finger_module.scad`): a spring-loaded plunger in a printed
  body — Ø8 mm conductive stylus tip (M3 grub screw), Ø6 mm shaft in a guide
  bore, Ø8 × 25 mm compression spring in a top pocket retained by the
  toolhead plate. A deploy servo (`finger_deploy`, MG90S) swings the body
  between stow (clear of the nest) and working (vertical) positions.
- **Button plungers** (`button_plunger.scad`): two nest-mounted MG90S servos
  (`plunger_0`, `plunger_1`) driving Ø6 mm pins through guide bores into the
  device's side buttons. Slotted bases give 10 mm of edge-distance adjustment
  on the deck grid.

### Tap force budget

Target contact force: **1.5–6 N** (below the force that slides a device in
rubber-padded stops, above the touchscreen's registration threshold).

The Z axis does not control force — the **spring** does. Spring rate
k ≈ 0.5 N/mm (Ø8 × 25 mm compression spring, typical assortment value). The
framework sets `touch_z` so the tip meets the glass with the spring already
compressed ~3 mm:

- 3 mm compression → 1.5 N (light tap)
- up to 12 mm → 6 N (firm press / worn screen protector)

Z positioning resolution (8 mm/rev ÷ 200 full steps ÷ 16 µsteps =
**2.5 µm/µstep**) sets the compression to within 0.05 mm (≈0.03 N) — well
below the ~0.1 N system repeatability from homing and spring tolerances. The
15 mm plunger stroke absorbs device-thickness tolerance; the servo stow keeps
the tip off the deck during device swaps.

## Device nest

`device_nest.scad`: two fixed `corner_stop` L-references + two sliding
`side_clamp`s (30 mm slots, M5 thumb tabs) on the deck's M4 grid. Holds
devices from phones to ~11" tablets (≤ 280 × 200 mm). All nest hardware is
≤ 8 mm tall — below the screen, out of the overhead camera's view of the
glass, and outside the 40 mm ArUco keep-out zones at the deck corners
(`NEST_CLEAR`; markers sit one marker-width, 20 mm, in from each corner — see
`config.py deck_marker_map`).

## Cameras

- **Overhead**: USB webcam on the 400 mm rear post (`overhead_clamp`). A
  ~60°-FoV webcam at 400 mm covers ~460 mm across — the full 400 mm deck with
  margin. Used for ArUco deck registration and screen OCR.
- **Toolhead**: USB webcam under the gantry plate (`toolcam_bracket`), for
  close-up verification of taps and button states.

## Printed parts

| File | Parts | Notes |
|------|-------|-------|
| `frame_brackets.scad` | corner_bracket, motor_plate, idler_mount | ×4 corners, ×3 motor (X/Y/tool-Z), ×6 idler |
| `gantry_carriage.scad` | toolhead_plate, belt_clamp | plate ×1, clamp ×2 |
| `finger_module.scad` | finger_body, deploy_arm | |
| `button_plunger.scad` | plunger_base, plunger_pin | ×2 of each |
| `device_nest.scad` | corner_stop, side_clamp | ×2 of each |
| `camera_mounts.scad` | overhead_clamp, toolcam_bracket | |

Print in PETG, 4 perimeters, 40% infill. Previews in `docs/img/`, STLs in
`cad/stl/` — regenerate both with
`powershell -ExecutionPolicy Bypass -File cad/openscad/render_previews.ps1`.
