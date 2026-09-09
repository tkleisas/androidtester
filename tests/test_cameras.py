"""Cameras: synthetic rendering, projection sanity, config-based selection."""

from __future__ import annotations

import numpy as np
import pytest

from androidtester.cameras import OpenCVCamera, SyntheticCamera, VirtualPose, camera_from_config
from androidtester.calib import detect_markers
from androidtester.config import HarnessConfig
from androidtester.devices import load_profile
from conftest import DEVICES_DIR


@pytest.fixture
def config() -> HarnessConfig:
    return HarnessConfig()


def test_synthetic_frame_contains_all_markers(config: HarnessConfig):
    detections = detect_markers(SyntheticCamera(config).grab())
    assert {d.marker_id for d in detections} == {1, 2, 3, 4}


def test_synthetic_marker_centers_match_projection(config: HarnessConfig):
    camera = SyntheticCamera(config)
    detections = {d.marker_id: d for d in detect_markers(camera.grab())}
    for marker_id, center_mm in config.deck_marker_map().items():
        (u, v), = camera.project([center_mm])
        detected = detections[marker_id].center
        assert abs(detected[0] - u) < 1.0 and abs(detected[1] - v) < 1.0


def test_synthetic_renders_device_screen(config: HarnessConfig):
    profile = load_profile(DEVICES_DIR / "example_phone.yaml")
    camera = SyntheticCamera(config, profile)
    frame = camera.grab()
    cx = sum(p[0] for p in profile.screen_polygon) / 4.0
    cy = sum(p[1] for p in profile.screen_polygon) / 4.0
    (u, v), = camera.project([(cx, cy)])
    pixel = frame[int(v), int(u)]
    assert tuple(pixel) == (60, 60, 60)  # dark screen patch, distinct from the deck


def test_pose_changes_the_projection(config: HarnessConfig):
    plain = SyntheticCamera(config, pose=VirtualPose(tilt_x_deg=0.0, tilt_y_deg=0.0, yaw_deg=0.0))
    tilted = SyntheticCamera(config)
    point = [(150.0, 150.0)]
    assert not np.allclose(plain.project(point), tilted.project(point))


def test_camera_from_config_selects_synthetic_by_default(config: HarnessConfig):
    assert isinstance(camera_from_config(config), SyntheticCamera)


def test_camera_from_config_selects_opencv_for_index():
    config = HarnessConfig(cameras={"overhead": "2"})
    camera = camera_from_config(config)
    assert isinstance(camera, OpenCVCamera)
    assert camera._source == 2


def test_camera_from_config_keeps_stream_urls():
    config = HarnessConfig(cameras={"overhead": "rtsp://rig.local/deck"})
    camera = camera_from_config(config)
    assert isinstance(camera, OpenCVCamera)
    assert camera._source == "rtsp://rig.local/deck"
