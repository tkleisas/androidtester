"""Harness ops: macro sequences, safety choreography, failure parking."""

from __future__ import annotations

import pytest

from androidtester.config import HarnessConfig
from androidtester.devices import load_profile
from androidtester.harness import Harness, HarnessError
from androidtester.motion import MotionError
from conftest import DEVICES_DIR


@pytest.fixture
def phone():
    return load_profile(DEVICES_DIR / "example_phone.yaml")


def make_harness(fake_client, phone, **overrides) -> Harness:
    config = HarnessConfig(**overrides)
    return Harness(fake_client, config, phone)


def test_finger_tap_goes_tools_up_first(fake_client, phone):
    harness = make_harness(fake_client, phone)
    harness.home()
    harness.finger_tap(95.75, 150.0)
    assert fake_client.scripts == [
        "HOME_ALL",
        "TOOLS_UP",
        "FINGER_TAP X=95.75 Y=150",
    ]


def test_finger_swipe_choreography(fake_client, phone):
    harness = make_harness(fake_client, phone)
    harness.home()
    harness.finger_swipe(95.75, 203.3, 95.75, 61.4, duration_s=0.5)
    scripts = fake_client.scripts
    assert scripts[0] == "HOME_ALL"
    assert scripts[-2] == "TOOLS_UP"
    assert scripts[-1] == "FINGER_SWIPE X1=95.75 Y1=203.3 X2=95.75 Y2=61.4 T=500"
    # tools-up must precede the contact macro
    assert scripts.index("TOOLS_UP") < scripts.index(scripts[-1])


def test_finger_long_press_choreography(fake_client, phone):
    harness = make_harness(fake_client, phone)
    harness.finger_long_press(95.75, 150.0, duration_s=1.2)
    assert fake_client.scripts == ["TOOLS_UP", "FINGER_LONG_PRESS X=95.75 Y=150 T=1200"]


def test_button_press_maps_to_plunger(fake_client, phone):
    harness = make_harness(fake_client, phone)
    harness.button_press("power")
    assert fake_client.scripts == ["TOOLS_UP", "BUTTON_PRESS PLUNGER=plunger_0"]


def test_button_press_unknown_button(fake_client, phone):
    harness = make_harness(fake_client, phone)
    with pytest.raises(HarnessError, match="no button named 'mute'"):
        harness.button_press("mute")


def test_point_outside_deck_rejected(fake_client, phone):
    harness = make_harness(fake_client, phone)
    with pytest.raises(HarnessError, match="outside the deck"):
        harness.finger_tap(401.0, 10.0)  # default deck is 400 x 300 mm (config.py)
    assert fake_client.scripts == []  # nothing was sent


def test_motion_failure_parks_before_raising(fake_client, phone):
    fake_client.fail_on = "FINGER_TAP"
    harness = make_harness(fake_client, phone)
    with pytest.raises(MotionError, match="injected failure"):
        harness.finger_tap(95.75, 150.0)
    assert fake_client.scripts[-1] == "PARK"


def test_dry_run_records_without_sending(fake_client, phone):
    harness = make_harness(fake_client, phone, dry_run=True)
    harness.home()
    harness.finger_tap(95.75, 150.0)
    harness.park()
    assert harness.recorded == ["HOME_ALL", "TOOLS_UP", "FINGER_TAP X=95.75 Y=150", "PARK"]
    assert fake_client.scripts == []
