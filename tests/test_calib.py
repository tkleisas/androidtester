"""Deck calibration: DLT solve, synthetic round-trip, loud failures, CLI."""

from __future__ import annotations

import numpy as np
import pytest

from androidtester import calib
from androidtester.calib import CalibrationError, calibrate_deck, detect_markers, solve_homography
from androidtester.cameras import SyntheticCamera
from androidtester.config import HarnessConfig

DECK_POINTS = [(30.0, 30.0), (150.0, 150.0), (270.0, 240.0), (63.0, 84.0), (128.5, 221.0)]


@pytest.fixture
def config() -> HarnessConfig:
    return HarnessConfig()


@pytest.fixture
def calibration(config: HarnessConfig):
    camera = SyntheticCamera(config)
    return camera, calibrate_deck(
        camera.grab(), config.deck_marker_map(), marker_size_mm=config.marker_size_mm
    )


def test_solve_homography_recovers_known_transform():
    rng = np.random.default_rng(7)
    src = rng.uniform(0, 100, size=(12, 2))
    angle, scale, offset = 0.3, 1.7, np.array([40.0, -15.0])
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    dst = scale * (src @ rot.T) + offset
    h = solve_homography(src, dst)
    mapped = (h @ np.hstack([src, np.ones((len(src), 1))]).T).T
    mapped = mapped[:, :2] / mapped[:, 2:]
    assert np.abs(mapped - dst).max() < 1e-6


def test_synthetic_homography_round_trip_sub_mm(calibration):
    camera, cal = calibration
    assert cal.rms_mm < 0.5
    projected = camera.project(DECK_POINTS)
    errors = [
        float(np.hypot(cal.px_to_deck(u, v)[0] - x, cal.px_to_deck(u, v)[1] - y))
        for (x, y), (u, v) in zip(DECK_POINTS, projected)
    ]
    assert max(errors) < 0.5


def test_deck_point_is_the_inverse_map(calibration):
    _, cal = calibration
    for x, y in DECK_POINTS:
        u, v = cal.deck_point(x, y)
        xr, yr = cal.px_to_deck(u, v)
        assert abs(xr - x) < 1e-6 and abs(yr - y) < 1e-6


def test_screen_polygon_px_matches_ground_truth(config: HarnessConfig):
    from androidtester.devices import load_profile
    from conftest import DEVICES_DIR

    profile = load_profile(DEVICES_DIR / "example_phone.yaml")
    camera = SyntheticCamera(config, profile)
    cal = calibrate_deck(
        camera.grab(), config.deck_marker_map(), marker_size_mm=config.marker_size_mm
    )
    truth = camera.project(profile.screen_polygon)
    mapped = cal.screen_polygon_px(profile.screen_polygon)
    # px tolerance for a 0.5 mm deck error at ~2 px/mm scale
    assert np.abs(mapped - truth).max() < 2.0


def test_missing_marker_is_named(config: HarnessConfig):
    markers = {**config.deck_marker_map(), 7: (150.0, 150.0)}  # id 7 is not rendered
    with pytest.raises(CalibrationError, match=r"\[7\]"):
        calibrate_deck(SyntheticCamera(config).grab(), markers)


def test_high_rms_fails_with_numbers(config: HarnessConfig):
    # Claim marker 3 sits 8 mm away from where it actually is: the fit must degrade.
    markers = config.deck_marker_map()
    markers[3] = (markers[3][0] - 8.0, markers[3][1] + 8.0)
    with pytest.raises(CalibrationError, match=r"RMS \d+\.\d+ mm exceeds the 0\.5 mm"):
        calibrate_deck(
            SyntheticCamera(config).grab(), markers,
            marker_size_mm=config.marker_size_mm, rms_below_mm=0.5,
        )


def test_rms_gate_respects_threshold(config: HarnessConfig):
    markers = config.deck_marker_map()
    markers[3] = (markers[3][0] - 8.0, markers[3][1] + 8.0)
    cal = calibrate_deck(
        SyntheticCamera(config).grab(), markers,
        marker_size_mm=config.marker_size_mm, rms_below_mm=50.0,
    )
    assert cal.rms_mm > 0.5  # a loose gate still reports the real error


def test_detect_markers_finds_all_configured(config: HarnessConfig):
    detections = detect_markers(SyntheticCamera(config).grab())
    assert {d.marker_id for d in detections} == set(config.deck_marker_map())


def test_cli_prints_and_saves_annotated_frame(tmp_path, capsys):
    rc = calib.main(["--out", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "RMS reprojection error" in out
    assert "id 1" in out
    annotated = list(tmp_path.glob("calibration_*.png"))
    assert len(annotated) == 1


def test_cli_reports_calibration_failure(tmp_path, capsys, monkeypatch):
    # The CLI config names marker 9, but the camera sees only the defaults.
    import yaml

    from androidtester import cameras

    monkeypatch.setattr(
        cameras, "camera_from_config",
        lambda config, profile=None: SyntheticCamera(HarnessConfig()),
    )
    cfg_path = tmp_path / "rig.yaml"
    cfg_path.write_text(yaml.safe_dump({"deck_markers": {9: [150.0, 150.0]}}), encoding="utf-8")
    rc = calib.main(["--config", str(cfg_path), "--out", str(tmp_path)])
    assert rc == 2
    assert "9" in capsys.readouterr().err
