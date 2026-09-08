"""Motion layer: a Moonraker HTTP client behind the MotionClient protocol.

`MoonrakerClient` talks to Klipper via Moonraker's HTTP API. `wait_idle` is
strict: any malformed status response is an error, never silently "idle".
`FakeMoonrakerClient` is the test double: it records the script queue and
models just enough machine state (homed flag, axis positions, busy polling)
to catch scripting mistakes in tests.
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

import requests


class MotionError(RuntimeError):
    """Raised on transport errors, malformed status, or invalid scripts."""


class MotionTimeout(MotionError):
    """Raised when the printer does not become idle within the deadline."""


@runtime_checkable
class MotionClient(Protocol):
    """Minimal motion interface the harness depends on."""

    def run_gcode_script(self, script: str) -> None:
        """Queue a G-code script for execution."""
        ...

    def printer_status(self) -> dict[str, Any]:
        """Return a status dict shaped like Moonraker's object query result."""
        ...


#: States Klipper reports via ``print_stats.state``.
KNOWN_STATES = frozenset({"standby", "printing", "paused", "cancelled", "complete", "error"})

#: States in which the machine is not executing anything.
_IDLE_STATES = frozenset({"standby", "cancelled", "complete"})


def _extract_motion_state(status: dict[str, Any]) -> tuple[str, float]:
    """Pull (print state, live velocity) out of a status dict, strictly."""
    if not isinstance(status, dict):
        raise MotionError(f"malformed printer status: expected mapping, got {type(status).__name__}")
    try:
        state = status["print_stats"]["state"]
        velocity = status["motion_report"]["live_velocity"]
    except (KeyError, TypeError) as exc:
        raise MotionError(f"malformed printer status: missing {exc}") from exc
    if not isinstance(state, str) or state not in KNOWN_STATES:
        raise MotionError(f"malformed printer status: unknown print_stats.state {state!r}")
    if isinstance(velocity, bool) or not isinstance(velocity, (int, float)):
        raise MotionError(f"malformed printer status: live_velocity {velocity!r} is not a number")
    return state, float(velocity)


def wait_idle(client: MotionClient, timeout_s: float = 60.0, poll_s: float = 0.25) -> None:
    """Block until the machine reports a non-moving state with zero velocity.

    Raises MotionError on a malformed status or a printer error state, and
    MotionTimeout when the deadline expires. Never guesses: anything the
    status does not state explicitly is treated as not-idle / broken.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        state, velocity = _extract_motion_state(client.printer_status())
        if state == "error":
            raise MotionError("printer is in error state")
        if state in _IDLE_STATES and velocity == 0.0:
            return
        if time.monotonic() >= deadline:
            raise MotionTimeout(f"printer still busy (state={state}, v={velocity}) after {timeout_s}s")
        time.sleep(poll_s)


class MoonrakerClient:
    """HTTP client for Moonraker's printer endpoints."""

    def __init__(self, base_url: str, *, request_timeout_s: float = 10.0, session: requests.Session | None = None):
        self._base = base_url.rstrip("/")
        self._timeout = request_timeout_s
        self._http = session or requests.Session()

    def run_gcode_script(self, script: str) -> None:
        if not script or not script.strip():
            raise MotionError("refusing to send an empty G-code script")
        try:
            resp = self._http.post(
                f"{self._base}/printer/gcode/script",
                json={"script": script},
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise MotionError(f"Moonraker rejected G-code script: {exc}") from exc

    def printer_status(self) -> dict[str, Any]:
        try:
            resp = self._http.get(
                f"{self._base}/printer/objects/query",
                params={"print_stats": None, "motion_report": None},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise MotionError(f"Moonraker status query failed: {exc}") from exc
        try:
            return payload["result"]["status"]
        except (KeyError, TypeError) as exc:
            raise MotionError(f"malformed Moonraker response: missing {exc}") from exc

    def wait_idle(self, timeout_s: float = 60.0, poll_s: float = 0.25) -> None:
        wait_idle(self, timeout_s, poll_s)


class FakeMoonrakerClient:
    """Test double: records scripts and models a strict-but-simple machine.

    State model: the machine starts un-homed; `G28`/`HOME_ALL` homes it; raw
    `G0`/`G1` moves before homing are rejected (the classic way to crash a
    gantry). `busy_status_calls` simulates motion in progress for that many
    status polls. Set `fail_on` to a substring to inject a failure when a
    matching script is sent.
    """

    def __init__(self, *, busy_status_calls: int = 0):
        self.scripts: list[str] = []
        self.homed: bool = False
        self.position: dict[str, float] = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self.fail_on: str | None = None
        self._busy = busy_status_calls

    # -- MotionClient interface -------------------------------------------

    def run_gcode_script(self, script: str) -> None:
        if not isinstance(script, str) or not script.strip():
            raise MotionError("empty G-code script")
        if self.fail_on and self.fail_on in script:
            raise MotionError(f"injected failure for script {script!r}")
        self.scripts.append(script)
        for line in script.splitlines():
            self._apply(line.strip())

    def printer_status(self) -> dict[str, Any]:
        if self._busy > 0:
            self._busy -= 1
            return {"print_stats": {"state": "printing"}, "motion_report": {"live_velocity": 12.5}}
        return {"print_stats": {"state": "standby"}, "motion_report": {"live_velocity": 0.0}}

    def wait_idle(self, timeout_s: float = 60.0, poll_s: float = 0.0) -> None:
        wait_idle(self, timeout_s, poll_s)

    # -- state model --------------------------------------------------------

    def _apply(self, line: str) -> None:
        if not line or line.startswith(";") or line.startswith("("):
            return
        command = line.split()[0].upper()
        if command in ("G28", "HOME_ALL"):
            self.homed = True
        elif command in ("G0", "G1"):
            if not self.homed:
                raise MotionError(f"move before homing: {line!r}")
            self._apply_move(line)
        elif command in ("G90", "G91", "G4", "M400"):
            pass  # positioning modes / dwell / drain: no state needed
        # Anything else (named macros, SET_SERVO, ...) is accepted verbatim.

    def _apply_move(self, line: str) -> None:
        for token in line.split()[1:]:
            axis, value = token[0].upper(), token[1:]
            if axis in self.position and value:
                try:
                    self.position[axis] = float(value)
                except ValueError as exc:
                    raise MotionError(f"bad move token {token!r} in {line!r}") from exc
