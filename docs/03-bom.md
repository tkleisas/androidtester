# 03 — Bill of materials

Rough 2025 street prices (EUR, EU shops/AliExpress average), quantities match
`docs/01-mechanical.md` and `docs/02-electronics.md`. The table's arithmetic
is checked by `tests/test_design_package.py` (per-row qty × unit = line, and
the rows sum to the stated total).

| # | Item | Spec / purpose | Qty | Unit € | Line € |
|---|------|----------------|-----|--------|--------|
| 1 | 2020 aluminium extrusion, 1 m | frame 500×400, posts, gantry beam, camera post (4.3 m cut plan) | 5 | 6.00 | 30.00 |
| 2 | 2020 corner bracket + T-nut/screw kit | frame joinery | 1 | 15.00 | 15.00 |
| 3 | MGN12H linear rail 500 mm + carriage | X axis (min 465: 400 travel + 45 carriage + 2×10 margin) | 1 | 18.00 | 18.00 |
| 4 | MGN12H linear rail 400 mm + carriage | Y axis pair (min 365) | 2 | 15.00 | 30.00 |
| 5 | MGN9H linear rail 150 mm + carriage | tool-Z (min 120) | 1 | 9.00 | 9.00 |
| 6 | NEMA17 stepper, 40 mm, 1.5 A | CoreXY A/B + tool-Z = 3 steppers | 3 | 12.00 | 36.00 |
| 7 | GT2 20T drive pulley, 5 mm bore | CoreXY A/B motors (tool-Z is lead-screw driven) | 2 | 1.50 | 3.00 |
| 8 | GT2 20T idler pulley, 5 mm bore | CoreXY belt returns | 6 | 1.50 | 9.00 |
| 9 | GT2 open belt, 6 mm, 5 m roll | CoreXY loop (~2 m) + spare | 1 | 8.00 | 8.00 |
| 10 | T8 lead screw, 8 mm lead, 150 mm + nut | tool-Z elevator (8 mm/rev) | 1 | 8.00 | 8.00 |
| 11 | Flexible shaft coupler 5→8 mm | tool-Z motor to lead screw | 1 | 3.00 | 3.00 |
| 12 | BIGTREETECH SKR Pico v1.0 | motion controller (RP2040, Klipper) | 1 | 35.00 | 35.00 |
| 13 | TMC2209 stepper driver | X, Y, tool-Z = 3 drivers | 3 | 6.00 | 18.00 |
| 14 | Raspberry Pi 4B, 2 GB | Klipper/Moonraker host + framework | 1 | 50.00 | 50.00 |
| 15 | microSD card 32 GB | Pi system | 1 | 8.00 | 8.00 |
| 16 | Endstop microswitch with lever | X-min, Y-min, tool-Z top | 3 | 1.00 | 3.00 |
| 17 | MG90S servo (metal gear) | plunger_0, plunger_1, finger_deploy | 3 | 4.00 | 12.00 |
| 18 | LM2596 buck module, 5 V/3 A | servo rail from 24 V | 1 | 3.00 | 3.00 |
| 19 | Meanwell LRS-150-24 PSU | 24 V motion + servo buck input | 1 | 25.00 | 25.00 |
| 20 | E-stop mushroom, 22 mm, 2-pole NC | power cut (motion + servo rails) | 1 | 6.00 | 6.00 |
| 21 | USB webcam 1080p | overhead + toolhead cameras | 2 | 12.00 | 24.00 |
| 22 | Conductive stylus tips, Ø8 mm | finger tool, consumable | 5 | 1.00 | 5.00 |
| 23 | Compression spring assortment, Ø8×25 | finger plunger, k ≈ 0.5 N/mm | 1 | 5.00 | 5.00 |
| 24 | Deck plate 400×300×4 mm, aluminium | M4 grid drilled for nest hardware | 1 | 12.00 | 12.00 |
| 25 | Wire/ferrule/JST-XH/Dupont kit | all cabling | 1 | 15.00 | 15.00 |
| 26 | PETG filament, ~0.5 kg | printed parts (0.4 kg estimated) | 1 | 10.00 | 10.00 |
| 27 | M3/M4/M5 bolt & nut kit | assembly | 1 | 10.00 | 10.00 |
| 28 | Cable drag chain 10×15 mm, 1 m | toolhead loom | 1 | 8.00 | 8.00 |

**Total: ≈ €418.00** (the exact sum of the Line € column; "≈" because unit
prices are rough). Not included: shipping, a USB-C cable for the Pi↔Pico
link, and the Android device under test.

## Sourcing notes

- Rails: "MGN12H" = the long carriage; vendor block-hole spacing varies
  (nominal M3 on 20×20 mm) — check the delivered blocks before bolting down
  `toolhead_plate`.
- Any SG90/MG90S-class 9 g servo fits the pockets; metal-gear MG90S survives
  plunger duty longer.
- The SKR Pico clones vary in TMC UART jumper labelling — the addresses
  (X=0, Z=1, Y=2) are what the cfg assumes; verify with `DUMP_TMC`.
