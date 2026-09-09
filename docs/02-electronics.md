# 02 — Electronics

## Controller: BIGTREETECH SKR Pico v1.0

Choice: **SKR Pico (RP2040)** running Klipper, hosted by a Raspberry Pi over
USB. Rationale:

- 4 TMC driver sockets for a machine that needs exactly **3 steppers**
  (CoreXY A/B + tool-Z) — no wasted board, no external drivers.
- Native Klipper support, RP2040 PWM on any GPIO (needed for 3 servos).
- Cheap (~€35), widely stocked, fully documented pinout; the Voron 0
  ecosystem proves the pin map.
- 24 V in, on-board 5 V — though we still power the Pi separately (see
  E-stop below).

The Raspberry Pi (4B, 2 GB) runs Klipper/Moonraker + the Python framework
and talks to the Pico over USB (`/dev/serial/by-id/...`, set in
`firmware/klipper/androidtester.cfg`).

## Pin map (matches `androidtester.cfg` exactly)

| Function | Pins | SKR Pico port |
|----------|------|---------------|
| X step / dir / en | gpio11 / gpio10 / !gpio12 | X driver socket |
| X endstop | ^gpio4 | X-STOP |
| Y step / dir / en | gpio6 / gpio5 / !gpio7 | Y driver socket |
| Y endstop | ^gpio3 | Y-STOP |
| tool-Z step / dir / en | gpio19 / gpio28 / !gpio2 | Z driver socket |
| tool-Z endstop (top) | ^gpio25 | Z-STOP |
| TMC2209 UART (all) | gpio9 RX / gpio8 TX | shared; addresses X=0, Z=1, Y=2 (socket MS jumpers) |
| plunger_0 servo | gpio29 | SERVO port |
| plunger_1 servo | gpio14 | E0 socket STEP pin |
| finger_deploy servo | gpio13 | E0 socket DIR pin |
| placeholder stepper_z | gpio16 / gpio22 / !gpio15, endstop ^gpio26 | FSC / PROBE / E0-EN / THB — **nothing attached** |

Two notes:

- **E0 socket stays empty.** The machine has no extruder; its STEP/DIR pins
  are repurposed as servo signals #2 and #3. Servo 5 V/GND comes from the
  servo buck (below), not from the board.
- **Placeholder `stepper_z`.** Klipper's `corexy` kinematics loads x/y/z
  rails unconditionally, so a dummy Z rail sits on free pins and is never
  homed or moved (`HOME_ALL` does `G28 X Y` only). The real tool elevator is
  `[manual_stepper tool_z]`, commanded exclusively via `MANUAL_STEPPER` from
  the macro contract — no G-code path can crash Z into the deck.

## Power budget

| Rail | Load | Worst case | Supply |
|------|------|-----------|--------|
| 24 V motion | 2× CoreXY NEMA17 @0.8 A RMS ≈ 2×15 W + tool-Z ≈ 10 W + board logic ≈ 5 W | ≈ 45 W | Meanwell LRS-150-24 (150 W) — >3× headroom |
| 5 V servo rail | 3× MG90S, stall 0.7 A each | ≈ 2.1 A ≈ 11 W | LM2596 buck 5 V/3 A from 24 V |
| 5 V Pi | Pi 4B + 2 USB webcams | ≈ 15 W | official 5 V/3 A USB-C supply |

## E-stop: power-cut, not firmware

A **2-pole NC mushroom** sits in series with the 24 V feed:

- pole 1 → SKR Pico VIN (kills steppers and board),
- pole 2 → servo buck input (kills the servo rail).

Motion power dies even if Klipper hangs; the Pi and cameras stay alive on
their own supply so the framework can capture the post-mortem frame and
report cleanly. This is why the Pi is *not* powered from the Pico's GPIO 5 V.
`M112` remains as the software layer on top.

## Wiring notes

- Endstops: lever microswitches, COM→G, NC→signal, `^` pull-ups as in the
  cfg. X/Y switches at the min ends; tool-Z switch at the **top** (home up,
  away from the deck).
- TMC2209s: set the MS jumpers for UART addresses X=0, Z=1, Y=2; one shared
  UART (gpio9/gpio8). Start at the cfg currents (0.8 A X/Y, 0.6 A tool-Z).
- Servos: signal wires from gpio29 (SERVO port) and the E0 STEP/DIR pads;
  5 V/GND from the buck. **Common ground** between buck output and SKR Pico
  GND is mandatory (the buck input shares 24 V GND with the board, which
  satisfies this).
- Toolhead loom (tool-Z motor, deploy servo, toolcam USB) in the 10×15 mm
  drag chain; leave USB-C camera leads strain-relieved at both ends.
- Bed/heater ports (gpio21/gpio23), fans (gpio17/18/20) and TH0 (gpio27) are
  unused; leave them unconfigured.
