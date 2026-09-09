"""Scenario runner: example scenarios, failures, reports, vision plumbing."""

from __future__ import annotations

import json

import numpy as np
import pytest

from androidtester.config import HarnessConfig
from androidtester.scenario import (
    ScenarioError,
    ScenarioRunner,
    run_scenario_file,
)
from androidtester.harness import Harness
from androidtester.devices import load_profile
from conftest import DEVICES_DIR, SCENARIOS_DIR, StaticCamera

PIN_ENV = "DEVICE_PIN_1"
EXAMPLE_SCENARIOS = ["smoke_wake_unlock", "app_regression", "tablet_rotation"]


class StubOCR:
    """OCR backend returning a canned text regardless of the image."""

    def __init__(self, text: str):
        self.text = text

    def read_text(self, image: np.ndarray) -> str:
        return self.text


@pytest.fixture
def pin(monkeypatch):
    monkeypatch.setenv(PIN_ENV, "1337")


@pytest.mark.parametrize("name", EXAMPLE_SCENARIOS)
def test_example_scenarios_pass_in_dry_run(name, pin, fake_client, tmp_path):
    result = run_scenario_file(
        SCENARIOS_DIR / f"{name}.yaml",
        config=HarnessConfig(dry_run=True),
        devices_dir=DEVICES_DIR,
        out_dir=tmp_path,
        client=fake_client,
    )
    assert result.passed, [s.detail for s in result.steps if s.status == "failed"]
    assert {s.phase for s in result.steps} == {"pre", "steps", "post"}
    assert fake_client.scripts == []  # dry-run: nothing was sent
    # reports landed
    report_dir = result.report_dir
    payload = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["passed"] and payload["dry_run"]
    assert len(payload["steps"]) == len(result.steps)
    assert (report_dir / "junit.xml").is_file()


def test_dry_run_records_macro_sequence(pin, fake_client, tmp_path):
    run_scenario_file(
        SCENARIOS_DIR / "smoke_wake_unlock.yaml",
        config=HarnessConfig(dry_run=True),
        devices_dir=DEVICES_DIR,
        out_dir=tmp_path,
        client=fake_client,
    )
    # re-run through the harness to inspect the recording
    from androidtester.scenario import _load_scenario

    config = HarnessConfig(dry_run=True)
    profile = load_profile(DEVICES_DIR / "example_phone.yaml")
    harness = Harness(fake_client, config, profile)
    runner = ScenarioRunner(harness)
    runner.run(_load_scenario(SCENARIOS_DIR / "smoke_wake_unlock.yaml"))
    assert harness.recorded[0] == "HOME_ALL"
    assert harness.recorded[-1] == "PARK"
    assert "BUTTON_PRESS PLUNGER=plunger_0" in harness.recorded
    # PIN 1337 = four finger taps at pin-pad positions
    taps = [s for s in harness.recorded if s.startswith("FINGER_TAP")]
    assert len(taps) == 4


def test_scenario_with_real_client_and_stub_ocr(pin, fake_client, tmp_path):
    """Non-dry run: motion goes to the fake client, vision via stub OCR."""
    from androidtester.cameras import SyntheticCamera

    config = HarnessConfig()
    camera = SyntheticCamera(config, load_profile(DEVICES_DIR / "example_phone.yaml"))
    ocr = StubOCR("Home screen")
    result = run_scenario_file(
        SCENARIOS_DIR / "smoke_wake_unlock.yaml",
        config=config,
        devices_dir=DEVICES_DIR,
        out_dir=tmp_path,
        client=fake_client,
        camera=camera,
        ocr=ocr,
    )
    assert result.passed
    assert fake_client.scripts[0] == "HOME_ALL"
    assert fake_client.scripts[-1] == "PARK"


ALL_TEXT = "Home screen Settings About phone Device name Gallery Portrait Landscape"


def test_uncalibrated_camera_keeps_m1_polygon_path(pin, fake_client, tmp_path):
    """Without camera.calibrate the profile polygon doubles as pixels (M1)."""
    scenario_path = tmp_path / "no_calib.yaml"
    scenario_path.write_text(
        "name: no_calib\ndevice: example_phone\n"
        "steps: [{screen.assert_text: {text: Home}}]\n",
        encoding="utf-8",
    )
    result = run_scenario_file(
        scenario_path,
        config=HarnessConfig(),
        devices_dir=DEVICES_DIR,
        out_dir=tmp_path,
        client=fake_client,
        camera=StaticCamera(np.zeros((300, 300, 3), dtype=np.uint8)),
        ocr=StubOCR("Home screen"),
    )
    assert result.passed
    assert result.calibration_rms_mm is None


@pytest.mark.parametrize("name", EXAMPLE_SCENARIOS)
def test_example_scenarios_pass_with_synthetic_camera(name, pin, fake_client, tmp_path):
    """Full non-dry run: camera.calibrate in pre, vision through the homography."""
    from androidtester.cameras import SyntheticCamera

    config = HarnessConfig()
    profile = load_profile(DEVICES_DIR / f"example_{'tablet' if name == 'tablet_rotation' else 'phone'}.yaml")
    camera = SyntheticCamera(config, profile)
    result = run_scenario_file(
        SCENARIOS_DIR / f"{name}.yaml",
        config=config,
        devices_dir=DEVICES_DIR,
        out_dir=tmp_path,
        client=fake_client,
        camera=camera,
        ocr=StubOCR(ALL_TEXT),
    )
    assert result.passed, [s.detail for s in result.steps if s.status == "failed"]
    calibrate_step = next(s for s in result.steps if s.action == "camera.calibrate")
    assert calibrate_step.phase == "pre" and "RMS" in calibrate_step.detail
    # the fit quality lands in the JSON report
    assert result.calibration_rms_mm is not None and result.calibration_rms_mm < 0.5
    payload = json.loads((result.report_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["calibration_rms_mm"] == pytest.approx(result.calibration_rms_mm)


def test_fraction_targets_map_through_screen_point(fake_client):
    """[0.5, 0.82] plain-fraction tap lands at the same deck mm as '50%, 82%'."""
    from androidtester.scenario import _load_scenario, _point

    profile = load_profile(DEVICES_DIR / "example_phone.yaml")
    assert _point([0.5, 0.82], profile) == profile.screen_point(0.5, 0.82)
    assert _point(["50%", "82%"], profile) == profile.screen_point(0.5, 0.82)
    assert _point([150, 90], profile) == (150.0, 90.0)  # numbers > 1 stay deck mm
    with pytest.raises(ScenarioError, match="mixed coordinate kinds"):
        _point([0.5, 90], profile)
    # and the tap macro carries the screen_point coordinates
    harness = Harness(fake_client, HarnessConfig(dry_run=True), profile)
    runner = ScenarioRunner(harness)
    runner.run({
        "name": "frac", "device": "example_phone",
        "steps": [{"touch.tap": {"at": [0.5, 0.82]}}],
    })
    x, y = profile.screen_point(0.5, 0.82)
    assert f"FINGER_TAP X={x:g} Y={y:g}" in harness.recorded


def test_missing_pin_env_fails_loudly(monkeypatch, fake_client, tmp_path):
    monkeypatch.delenv(PIN_ENV, raising=False)
    result = run_scenario_file(
        SCENARIOS_DIR / "smoke_wake_unlock.yaml",
        config=HarnessConfig(dry_run=True),
        devices_dir=DEVICES_DIR,
        out_dir=tmp_path,
        client=fake_client,
    )
    assert not result.passed
    failed = [s for s in result.steps if s.status == "failed"]
    assert len(failed) == 1
    assert failed[0].action == "touch.enter_pin"
    assert PIN_ENV in failed[0].detail
    # steps after the failure are skipped, but the post phase still parks
    statuses = {s.action: s.status for s in result.steps}
    assert statuses["screen.wait_for"] == "skipped"
    assert statuses["park"] == "passed"
    # the failure is visible in the JUnit report
    assert "failure" in (result.report_dir / "junit.xml").read_text(encoding="utf-8")


def test_unknown_action_is_rejected(pin, fake_client):
    scenario = {
        "name": "bad",
        "device": "example_phone",
        "steps": [{"touch.flick": {}}],
    }
    harness = Harness(fake_client, HarnessConfig(dry_run=True), load_profile(DEVICES_DIR / "example_phone.yaml"))
    runner = ScenarioRunner(harness)
    with pytest.raises(ScenarioError, match="unknown action 'touch.flick'"):
        runner.run(scenario)


def test_vision_step_without_camera_fails_when_not_dry_run(pin, fake_client, tmp_path):
    result = run_scenario_file(
        SCENARIOS_DIR / "smoke_wake_unlock.yaml",
        config=HarnessConfig(),
        devices_dir=DEVICES_DIR,
        out_dir=tmp_path,
        client=fake_client,
    )
    assert not result.passed
    failed = [s for s in result.steps if s.status == "failed"][0]
    assert "requires a camera" in failed.detail


def test_unknown_device_profile_fails(pin, fake_client, tmp_path):
    from androidtester.devices import ProfileValidationError

    scenario_path = tmp_path / "ghost.yaml"
    scenario_path.write_text("name: ghost\ndevice: nope\nsteps: []\n", encoding="utf-8")
    with pytest.raises(ProfileValidationError, match="no device profile named 'nope'"):
        run_scenario_file(scenario_path, devices_dir=DEVICES_DIR, client=fake_client)
