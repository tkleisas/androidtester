"""Motion layer: fake client state model and wait_idle strictness."""

from __future__ import annotations

import pytest

from androidtester.motion import (
    FakeMoonrakerClient,
    MotionError,
    MotionTimeout,
    wait_idle,
)


class StubStatusClient:
    """Minimal client returning a canned status for wait_idle tests."""

    def __init__(self, status):
        self._status = status

    def run_gcode_script(self, script: str) -> None:  # pragma: no cover - unused
        pass

    def printer_status(self):
        return self._status


def test_fake_records_scripts_and_tracks_state(fake_client):
    fake_client.run_gcode_script("G28")
    fake_client.run_gcode_script("G1 X10.5 Y20 F3000")
    assert fake_client.scripts == ["G28", "G1 X10.5 Y20 F3000"]
    assert fake_client.homed
    assert fake_client.position == {"X": 10.5, "Y": 20.0, "Z": 0.0}


def test_fake_rejects_move_before_homing(fake_client):
    with pytest.raises(MotionError, match="move before homing"):
        fake_client.run_gcode_script("G1 X10")


def test_fake_rejects_empty_script(fake_client):
    with pytest.raises(MotionError, match="empty G-code script"):
        fake_client.run_gcode_script("   ")


def test_fake_accepts_macros_verbatim(fake_client):
    fake_client.run_gcode_script("HOME_ALL")
    fake_client.run_gcode_script("FINGER_TAP X=95.75 Y=150")
    assert fake_client.homed


def test_wait_idle_returns_when_standby_and_still():
    client = StubStatusClient({"print_stats": {"state": "standby"}, "motion_report": {"live_velocity": 0.0}})
    wait_idle(client, timeout_s=1.0)


def test_wait_idle_waits_out_busy_periods(fake_client):
    fake_client._busy = 2
    wait_idle(fake_client, timeout_s=5.0, poll_s=0.001)
    assert fake_client._busy == 0


def test_wait_idle_times_out_when_never_idle():
    client = StubStatusClient({"print_stats": {"state": "printing"}, "motion_report": {"live_velocity": 8.0}})
    with pytest.raises(MotionTimeout, match="still busy"):
        wait_idle(client, timeout_s=0.05, poll_s=0.01)


def test_wait_idle_raises_on_printer_error_state():
    client = StubStatusClient({"print_stats": {"state": "error"}, "motion_report": {"live_velocity": 0.0}})
    with pytest.raises(MotionError, match="error state"):
        wait_idle(client, timeout_s=1.0)


@pytest.mark.parametrize(
    "status",
    [
        {"motion_report": {"live_velocity": 0.0}},                                  # missing print_stats
        {"print_stats": {"state": "standby"}},                                       # missing motion_report
        {"print_stats": {"state": "galloping"}, "motion_report": {"live_velocity": 0.0}},  # unknown state
        {"print_stats": {"state": "standby"}, "motion_report": {"live_velocity": "fast"}},  # bad velocity
        "not a mapping",
    ],
)
def test_wait_idle_treats_malformed_status_as_error(status):
    client = StubStatusClient(status)
    with pytest.raises(MotionError, match="malformed printer status"):
        wait_idle(client, timeout_s=1.0)
