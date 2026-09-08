# AndroidTester

An **open-hardware robot that physically tests Android phones**. A gantry places
the device on a fixture and executes automated scenarios against it with **real
touch, real buttons, and real NFC** — the inputs a user (or a certification lab)
produces, not the inputs a debug bridge injects.

Everything is 3D-printable mechanics, commodity open electronics (Raspberry Pi +
Klipper, the 3D-printer firmware), and a Python framework that turns YAML
scenarios into motion + vision actions.

## Why physical, when ADB exists?

ADB/UI Automator can drive an app, but they can't:

- inject a **capacitive touch event the touchscreen controller actually felt**
  (edge rejection, glove/wet-finger behavior, screen-protector sensitivity),
- press the **physical power/volume buttons**,
- present a **contactless card to the NFC antenna** at a real position and angle
  (antenna sweet spots vary wildly between phone models),
- verify behavior with the device in its shipping state.

**Everything is physical.** Input is real fingers, real buttons, real cards;
verification is the **camera** — OCR and image checks on the screen as a user
would see it. Fully black-box: works on production builds, no USB debugging, no
agent on the device. The acceptance rule: *a scenario must pass with the
phone's USB port unplugged.*

## The machine

- **CoreXY gantry** (3D-printer kinematics) moves a toolhead over the deck.
- **Tool-Z elevator** adapts the tools to device thickness and button height.
- **Finger tool** with a conductive tip taps, swipes, and long-presses the
  touchscreen; small servo plungers in the nest press recessed side buttons.
- **Card manipulator** picks an emulator card from a dock and presents it to the
  phone's NFC antenna zone — tap-to-pay, card emulation, accessory pairing.
- **Cameras** (overhead + toolhead) register the deck and read the screen:
  ArUco homography, perspective rectification, OCR.
- **Klipper on a Raspberry Pi** drives motion; the Python framework talks to it
  over Moonraker and never issues raw moves below a safety clearance plane.

## The framework

YAML scenarios become motion + vision steps with per-step timeouts, artifact
capture, and JSON/JUnit reports:

```yaml
# scenarios/smoke_wake_unlock.yaml (excerpt)
steps:
  - button.press: { key: power }        # servo plunger on the side button
  - touch.swipe: { from: [50%, 90%], to: [50%, 20%] }
  - touch.enter_pin: { pin_env: DEVICE_PIN_1 }   # secrets from env, never the repo
  - screen.wait_for: { text: "Home", timeout_s: 10 }
```

- **Device profiles** (`devices/*.yaml`): screen polygon, physical-button map,
  NFC antenna zone, launcher layout, per-model quirks. New phone = new YAML,
  not new code.
- **Phone actions**: `touch.tap/swipe/long_press/enter_pin`, `button.press`,
  `nfc.present`, `screen.wait_for/assert_text/assert_image`.
- **Example scenarios**: `smoke_wake_unlock`, `app_regression` (golden-path tap
  flow with OCR assertions), `nfc_tap_payment` (launch a payment app, amount
  entry by touch, card presentation, approval screen read back by OCR).

## Digital twin

[steropes](https://github.com/tkleisas/steropes) — a 3D physics-based digital
twin for robotic test hardware — is the development companion: the machine's
motion, cameras, and device screen are simulated so the framework and vision
pipeline run before (and without) hardware.

## Roadmap

- **M0 — Machine design package**: parametric OpenSCAD parts, Klipper config,
  electronics, BOM (generalized gantry design, published as open hardware).
- **M1 — Framework**: motion client, scenario engine, vision pipeline, reports.
- **M2 — Phone nest + device profiles**: clamps, side-button pressers, first
  device YAMLs.
- **M3 — NFC**: card manipulator integration, antenna-zone mapping per device.
- **M4 — Twin parity**: steropes models the full machine + phone DUT.

## Status

Scaffold. The concept and architecture are set down here; the design package
and framework land with M0/M1.

## License

[MIT](LICENSE) — do what you want, attribution appreciated.
