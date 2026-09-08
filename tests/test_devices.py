"""Device profile schema: loading, geometry mapping, validation errors."""

from __future__ import annotations

import pytest

from androidtester.devices import (
    ProfileValidationError,
    load_profile,
    load_profile_by_name,
    profile_from_dict,
)
from conftest import DEVICES_DIR


def minimal_profile() -> dict:
    return {
        "name": "unit",
        "class": "phone",
        "body": {"width_mm": 70, "height_mm": 140, "thickness_mm": 9},
        "screen_polygon": [[0, 0], [70, 0], [70, 140], [0, 140]],
    }


def test_example_profiles_load():
    phone = load_profile(DEVICES_DIR / "example_phone.yaml")
    tablet = load_profile(DEVICES_DIR / "example_tablet.yaml")
    assert phone.device_class == "phone"
    assert tablet.device_class == "tablet"
    assert "power" in phone.buttons
    assert all(f"pin_{d}" in phone.launcher for d in "0123456789")


def test_load_profile_by_name_unknown():
    with pytest.raises(ProfileValidationError, match="no device profile named 'nope'"):
        load_profile_by_name("nope", DEVICES_DIR)


def test_screen_point_maps_fractions_to_deck_mm():
    profile = profile_from_dict(minimal_profile())
    assert profile.screen_point(0.0, 0.0) == (0.0, 0.0)
    assert profile.screen_point(1.0, 1.0) == (70.0, 140.0)
    assert profile.screen_point(0.5, 0.5) == (35.0, 70.0)


@pytest.mark.parametrize(
    ("mutate", "field_in_message"),
    [
        (lambda d: d.update({"class": "phablet"}), "class"),
        (lambda d: d.update({"name": ""}), "name"),
        (lambda d: d["body"].update({"width_mm": -5}), "body.width_mm"),
        (lambda d: d["body"].update({"height_mm": "tall"}), "body.height_mm"),
        (lambda d: d.update({"screen_polygon": [[0, 0], [1, 1]]}), "screen_polygon"),
        (lambda d: d.update({"screen_polygon": [[0, 0], [1, 1], [2, 2], [3]]}), "screen_polygon[3]"),
        (lambda d: d.update({"buttons": {"power": {"position": [1, 2], "plunger": "p0"}}}), "buttons.power.position"),
        (lambda d: d.update({"buttons": {"power": {"position": [1, 2, 3]}}}), "buttons.power.plunger"),
        (lambda d: d.update({"launcher": {"settings": {"x": 1.5, "y": 0.5}}}), "launcher.settings"),
        (lambda d: d.update({"quirks": ["not", "a", "mapping"]}), "quirks"),
    ],
)
def test_validation_errors_name_the_field(mutate, field_in_message):
    data = minimal_profile()
    mutate(data)
    with pytest.raises(ProfileValidationError) as excinfo:
        profile_from_dict(data, source="test.yaml")
    assert field_in_message in str(excinfo.value)
