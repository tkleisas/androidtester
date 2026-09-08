"""YAML scenario runner: pre/steps/post phases, timeouts, JSON + JUnit reports.

A scenario names a device profile and a list of single-key action steps:

    name: smoke_wake_unlock
    device: example_phone
    pre:   [{home: {}}]
    steps:
      - button.press: {key: power}
      - touch.swipe: {from: [50%, 90%], to: [50%, 20%]}
      - touch.enter_pin: {pin_env: DEVICE_PIN_1}   # secrets from env, never the repo
      - screen.wait_for: {text: "Home", timeout_s: 10}
    post:  [{park: {}}]

Coordinates are deck mm numbers or "NN%" strings (screen-relative fractions).
The `post` phase always runs — even after a failure — so the machine parks.

CLI: python -m androidtester.scenario scenarios/<file>.yaml [--dry-run] [--out out]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
import yaml

from .config import HarnessConfig
from .devices import DeviceProfile, load_profile_by_name
from .harness import Harness
from .motion import MotionClient, MoonrakerClient
from . import vision


class ScenarioError(RuntimeError):
    """Raised for malformed scenarios, missing secrets, unknown actions."""


@dataclass
class StepResult:
    index: int
    phase: str
    action: str
    status: str  # "passed" | "failed" | "skipped"
    duration_s: float
    detail: str = ""


@dataclass
class ScenarioResult:
    name: str
    device: str
    dry_run: bool
    steps: list[StepResult] = field(default_factory=list)
    duration_s: float = 0.0
    report_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return all(step.status != "failed" for step in self.steps)


#: Actions the runner dispatches; anything else is rejected loudly.
KNOWN_ACTIONS = frozenset({
    "home",
    "park",
    "touch.tap",
    "touch.swipe",
    "touch.long_press",
    "touch.enter_pin",
    "button.press",
    "screen.wait_for",
    "screen.assert_text",
    "screen.assert_image",
})


def _load_scenario(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ScenarioError(f"cannot read scenario {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ScenarioError(f"{path}: top level must be a mapping")
    for required in ("name", "device", "steps"):
        if required not in data:
            raise ScenarioError(f"{path}: missing required field {required!r}")
    return data


def _point(value: Any, profile: DeviceProfile) -> tuple[float, float]:
    """Resolve [x, y] as deck mm numbers or "NN%" screen fractions."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ScenarioError(f"expected a coordinate pair [x, y], got {value!r}")
    fractions: list[float] = []
    absolute: list[float] = []
    kinds = set()
    for item in value:
        if isinstance(item, str) and item.strip().endswith("%"):
            try:
                fractions.append(float(item.strip()[:-1]) / 100.0)
            except ValueError:
                raise ScenarioError(f"bad percentage coordinate {item!r}") from None
            kinds.add("fraction")
        elif isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ScenarioError(f"bad coordinate {item!r}: use deck mm or 'NN%'")
        else:
            absolute.append(float(item))
            kinds.add("absolute")
    if kinds == {"fraction"}:
        return profile.screen_point(fractions[0], fractions[1])
    if kinds == {"absolute"}:
        return (absolute[0], absolute[1])
    raise ScenarioError(f"mixed coordinate kinds in {value!r}: use both mm or both 'NN%'")


class ScenarioRunner:
    """Executes one scenario against a harness (+ optional camera/OCR)."""

    def __init__(
        self,
        harness: Harness,
        *,
        camera: vision.Camera | None = None,
        ocr: vision.OCRBackend | None = None,
        scenario_dir: Path | None = None,
    ):
        self.harness = harness
        self.camera = camera
        self.ocr = ocr
        self.scenario_dir = scenario_dir or Path.cwd()

    @property
    def profile(self) -> DeviceProfile:
        if self.harness.device is None:
            raise ScenarioError("runner requires a device profile on the harness")
        return self.harness.device

    # -- phases -------------------------------------------------------------

    def run(self, scenario: dict[str, Any], *, out_dir: Path | None = None) -> ScenarioResult:
        result = ScenarioResult(
            name=str(scenario["name"]),
            device=str(scenario["device"]),
            dry_run=self.harness.dry_run,
        )
        started = time.monotonic()
        try:
            for phase in ("pre", "steps"):
                self._run_phase(phase, scenario.get(phase, []), result)
        finally:
            # The post phase (park) runs even after a failure.
            try:
                self._run_phase("post", scenario.get("post", []), result)
            except Exception as exc:  # a parking failure must surface, not vanish
                result.steps.append(StepResult(len(result.steps), "post", "post", "failed", 0.0, str(exc)))
            result.duration_s = time.monotonic() - started
        if out_dir is not None:
            result.report_dir = write_reports(result, out_dir)
        return result

    def _run_phase(self, phase: str, steps: Any, result: ScenarioResult) -> None:
        if not isinstance(steps, list):
            raise ScenarioError(f"phase {phase!r} must be a list of steps, got {type(steps).__name__}")
        # The post phase (park) always executes, even after earlier failures.
        failed = phase != "post" and any(s.status == "failed" for s in result.steps)
        for step in steps:
            index = len(result.steps)
            action, params = self._parse_step(step)
            if failed:
                result.steps.append(StepResult(index, phase, action, "skipped", 0.0, "earlier step failed"))
                continue
            started = time.monotonic()
            try:
                detail = self._dispatch(action, params, step_timeout(step))
            except Exception as exc:
                result.steps.append(
                    StepResult(index, phase, action, "failed", time.monotonic() - started, str(exc))
                )
                failed = phase != "post"
            else:
                result.steps.append(StepResult(index, phase, action, "passed", time.monotonic() - started, detail))

    @staticmethod
    def _parse_step(step: Any) -> tuple[str, dict[str, Any]]:
        if not isinstance(step, dict) or len(step) != 1:
            raise ScenarioError(f"each step must be a single-key mapping, got {step!r}")
        action, params = next(iter(step.items()))
        if action not in KNOWN_ACTIONS:
            raise ScenarioError(f"unknown action {action!r} (known: {', '.join(sorted(KNOWN_ACTIONS))})")
        return action, (params or {})

    # -- actions --------------------------------------------------------------

    def _dispatch(self, action: str, params: dict[str, Any], timeout_s: float | None) -> str:
        handler = {
            "home": self._do_home,
            "park": self._do_park,
            "touch.tap": self._do_tap,
            "touch.swipe": self._do_swipe,
            "touch.long_press": self._do_long_press,
            "touch.enter_pin": self._do_enter_pin,
            "button.press": self._do_button_press,
            "screen.wait_for": self._do_wait_for,
            "screen.assert_text": self._do_assert_text,
            "screen.assert_image": self._do_assert_image,
        }[action]
        return handler(params, timeout_s)

    def _do_home(self, params: dict, timeout_s: float | None) -> str:
        self.harness.home()
        return "homed"

    def _do_park(self, params: dict, timeout_s: float | None) -> str:
        self.harness.park()
        return "parked"

    def _do_tap(self, params: dict, timeout_s: float | None) -> str:
        x, y = _point(params.get("at"), self.profile)
        self.harness.finger_tap(x, y)
        return f"tap at ({x:.1f}, {y:.1f})"

    def _do_swipe(self, params: dict, timeout_s: float | None) -> str:
        x1, y1 = _point(params.get("from"), self.profile)
        x2, y2 = _point(params.get("to"), self.profile)
        duration = float(params.get("duration_s", 0.4))
        self.harness.finger_swipe(x1, y1, x2, y2, duration)
        return f"swipe ({x1:.1f}, {y1:.1f}) -> ({x2:.1f}, {y2:.1f})"

    def _do_long_press(self, params: dict, timeout_s: float | None) -> str:
        x, y = _point(params.get("at"), self.profile)
        duration = float(params.get("duration_s", 1.0))
        self.harness.finger_long_press(x, y, duration)
        return f"long press at ({x:.1f}, {y:.1f}) for {duration}s"

    def _do_enter_pin(self, params: dict, timeout_s: float | None) -> str:
        env_name = params.get("pin_env")
        if not isinstance(env_name, str) or not env_name:
            raise ScenarioError(f"touch.enter_pin requires 'pin_env' naming an env var, got {env_name!r}")
        pin = os.environ.get(env_name)
        if pin is None:
            raise ScenarioError(
                f"PIN environment variable {env_name!r} is not set; "
                "secrets come from the environment, never the repo"
            )
        if not pin.isdigit():
            raise ScenarioError(f"PIN from {env_name!r} must be digits only")
        settle_s = float(self.profile.quirks.get("key_settle_s", 0.15))
        for digit in pin:
            entry = self.profile.launcher.get(f"pin_{digit}")
            if entry is None:
                raise ScenarioError(
                    f"device {self.profile.name!r} has no launcher entry 'pin_{digit}' for PIN entry"
                )
            x, y = self.profile.screen_point(entry.x, entry.y)
            self.harness.finger_tap(x, y)
            if settle_s and not self.harness.dry_run:
                time.sleep(settle_s)
        return f"entered {len(pin)}-digit PIN from env {env_name}"

    def _do_button_press(self, params: dict, timeout_s: float | None) -> str:
        key = params.get("key")
        if not isinstance(key, str) or not key:
            raise ScenarioError(f"button.press requires 'key' naming a profile button, got {key!r}")
        self.harness.button_press(key)
        return f"pressed button {key!r}"

    # -- vision actions ---------------------------------------------------------

    def _screen(self) -> np.ndarray:
        if self.camera is None:
            if self.harness.dry_run:
                raise _DryRunVision()
            raise ScenarioError("vision step requires a camera (or run with --dry-run)")
        frame = self.camera.grab()
        # The profile polygon is in deck mm; the camera's deck registration
        # (ArUco homography -> px) is M2 territory, so for now the camera is
        # expected to deliver an already deck-registered frame.
        return vision.rectify_screen(frame, self.profile.screen_polygon)

    def _check_text(self, text: str) -> None:
        vision.assert_text(self._screen(), text, ocr=self.ocr)

    def _do_wait_for(self, params: dict, timeout_s: float | None) -> str:
        text = params.get("text")
        if not isinstance(text, str) or not text:
            raise ScenarioError(f"screen.wait_for requires non-empty 'text', got {text!r}")
        timeout = float(params.get("timeout_s", timeout_s or 10.0))
        try:
            vision.wait_for(
                lambda: self._check_text(text) or "ok",
                timeout_s=timeout,
                description=f"text {text!r} on screen",
            )
        except _DryRunVision:
            return f"dry-run: text {text!r} not verified"
        return f"saw text {text!r}"

    def _do_assert_text(self, params: dict, timeout_s: float | None) -> str:
        text = params.get("text")
        if not isinstance(text, str) or not text:
            raise ScenarioError(f"screen.assert_text requires non-empty 'text', got {text!r}")
        try:
            self._check_text(text)
        except _DryRunVision:
            return f"dry-run: text {text!r} not verified"
        return f"text {text!r} present"

    def _do_assert_image(self, params: dict, timeout_s: float | None) -> str:
        template_name = params.get("template")
        if not isinstance(template_name, str) or not template_name:
            raise ScenarioError(f"screen.assert_image requires 'template' image path, got {template_name!r}")
        template_path = self.scenario_dir / template_name
        template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            raise ScenarioError(f"cannot read template image {template_path}")
        threshold = float(params.get("threshold", 0.85))
        try:
            score = vision.assert_image(self._screen(), template, threshold=threshold)
        except _DryRunVision:
            return f"dry-run: template {template_name!r} not verified"
        return f"template {template_name!r} matched ({score:.3f})"


class _DryRunVision(Exception):
    """Internal: marks a vision check skipped under --dry-run."""


def step_timeout(step: Any) -> float | None:
    """Per-step timeout in seconds, declared inside the step's params."""
    if isinstance(step, dict) and len(step) == 1:
        params = next(iter(step.values()))
        if isinstance(params, dict) and "timeout_s" in params:
            return float(params["timeout_s"])
    return None


# -- reports ------------------------------------------------------------------


def write_reports(result: ScenarioResult, out_dir: Path) -> Path:
    """Write report.json + junit.xml for one run; returns the report dir."""
    report_dir = out_dir / f"{result.name}_{time.strftime('%Y%m%d_%H%M%S')}"
    report_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "name": result.name,
        "device": result.device,
        "dry_run": result.dry_run,
        "passed": result.passed,
        "duration_s": round(result.duration_s, 3),
        "steps": [
            {
                "index": s.index,
                "phase": s.phase,
                "action": s.action,
                "status": s.status,
                "duration_s": round(s.duration_s, 3),
                "detail": s.detail,
            }
            for s in result.steps
        ],
    }
    (report_dir / "report.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    suite = ET.Element(
        "testsuite",
        {
            "name": result.name,
            "tests": str(len(result.steps)),
            "failures": str(sum(1 for s in result.steps if s.status == "failed")),
            "skipped": str(sum(1 for s in result.steps if s.status == "skipped")),
            "time": f"{result.duration_s:.3f}",
        },
    )
    for step in result.steps:
        case = ET.SubElement(
            suite,
            "testcase",
            {"classname": f"{result.name}.{step.phase}", "name": f"{step.index}:{step.action}", "time": f"{step.duration_s:.3f}"},
        )
        if step.status == "failed":
            failure = ET.SubElement(case, "failure", {"message": step.detail})
            failure.text = step.detail
        elif step.status == "skipped":
            ET.SubElement(case, "skipped", {"message": step.detail})
    ET.ElementTree(suite).write(report_dir / "junit.xml", encoding="utf-8", xml_declaration=True)
    return report_dir


# -- entry point -----------------------------------------------------------------


def run_scenario_file(
    scenario_path: str | Path,
    *,
    config: HarnessConfig | None = None,
    devices_dir: str | Path = "devices",
    out_dir: str | Path | None = None,
    client: MotionClient | None = None,
    camera: vision.Camera | None = None,
    ocr: vision.OCRBackend | None = None,
) -> ScenarioResult:
    """Load and run a scenario file; injectable client/camera for tests and twin."""
    scenario_path = Path(scenario_path)
    scenario = _load_scenario(scenario_path)
    config = config or HarnessConfig()
    profile = load_profile_by_name(str(scenario["device"]), devices_dir)
    if client is None:
        client = MoonrakerClient(config.moonraker_url)
    harness = Harness(client, config, profile)
    runner = ScenarioRunner(harness, camera=camera, ocr=ocr, scenario_dir=scenario_path.parent)
    return runner.run(scenario, out_dir=Path(out_dir) if out_dir else None)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="androidtester.scenario", description="Run a YAML test scenario.")
    parser.add_argument("scenario", help="path to the scenario YAML")
    parser.add_argument("--config", help="harness config YAML (defaults applied otherwise)")
    parser.add_argument("--devices", default="devices", help="device profiles directory")
    parser.add_argument("--out", default="out", help="artifact output directory")
    parser.add_argument("--dry-run", action="store_true", help="record actions, send nothing, skip vision")
    args = parser.parse_args(argv)

    config = HarnessConfig.load(args.config) if args.config else HarnessConfig()
    if args.dry_run:
        config = HarnessConfig.from_dict({**config.__dict__, "dry_run": True})

    try:
        result = run_scenario_file(
            args.scenario,
            config=config,
            devices_dir=args.devices,
            out_dir=args.out,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for step in result.steps:
        mark = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[step.status]
        print(f"[{mark}] {step.phase:5s} {step.action}: {step.detail}")
    status = "PASSED" if result.passed else "FAILED"
    print(f"scenario {result.name!r} {status} in {result.duration_s:.2f}s (report: {result.report_dir})")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
