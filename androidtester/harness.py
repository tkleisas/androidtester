"""High-level machine operations with the safety choreography.

Every op maps to Klipper macros (see `firmware/klipper/androidtester.cfg`).
The rules, enforced here and again in firmware:

- tools travel up to the clearance plane (`TOOLS_UP`) before any XY travel,
- the finger only descends to the touch plane for the contact itself,
- any motion error parks the machine before the exception propagates.

In `dry_run` mode ops are recorded in `Harness.recorded` and nothing is sent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .config import HarnessConfig
from .motion import MotionClient, MotionError, wait_idle

if TYPE_CHECKING:
    from .devices import DeviceProfile


class HarnessError(RuntimeError):
    """Raised for bad op requests (unknown button, out-of-deck coordinates)."""


def _fmt(value: float) -> str:
    """Format a macro parameter compactly (95.75, not 95.750000)."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


class Harness:
    """Drives one rig (motion client + config) against one device profile."""

    def __init__(self, client: MotionClient, config: HarnessConfig, device: DeviceProfile | None = None):
        self._client = client
        self._config = config
        self.device = device
        self.recorded: list[str] = []

    @property
    def dry_run(self) -> bool:
        return self._config.dry_run

    @property
    def config(self) -> HarnessConfig:
        return self._config

    # -- plumbing -----------------------------------------------------------

    def _gcode(self, name: str, **params: float | str) -> None:
        """Send one macro invocation, recording instead in dry-run mode."""
        script = name
        if params:
            script += " " + " ".join(
                f"{key}={value if isinstance(value, str) else _fmt(value)}" for key, value in params.items()
            )
        if self._config.dry_run:
            self.recorded.append(script)
            return
        try:
            self._client.run_gcode_script(script)
        except MotionError:
            self._safe_park()
            raise

    def _safe_park(self) -> None:
        """Best-effort park after a failure; never masks the original error."""
        try:
            self._client.run_gcode_script("PARK")
        except Exception:
            pass

    def _wait_idle(self) -> None:
        if not self._config.dry_run:
            wait_idle(self._client, timeout_s=self._config.idle_timeout_s)

    def _check_xy(self, x: float, y: float) -> None:
        if not (0.0 <= x <= self._config.deck_width_mm and 0.0 <= y <= self._config.deck_height_mm):
            raise HarnessError(
                f"point ({x}, {y}) is outside the deck "
                f"({self._config.deck_width_mm} x {self._config.deck_height_mm} mm)"
            )

    # -- ops ----------------------------------------------------------------

    def home(self) -> None:
        """Home all axes; required before any move."""
        self._gcode("HOME_ALL")
        self._wait_idle()

    def park(self) -> None:
        """Tools up and off the device; the safe end state of every run."""
        self._gcode("PARK")
        self._wait_idle()

    def finger_tap(self, x: float, y: float) -> None:
        """Tap the touchscreen at deck mm (x, y)."""
        self._check_xy(x, y)
        self._gcode("TOOLS_UP")
        self._gcode("FINGER_TAP", X=x, Y=y)
        self._wait_idle()

    def finger_swipe(self, x1: float, y1: float, x2: float, y2: float, duration_s: float = 0.4) -> None:
        """Swipe the touchscreen from (x1, y1) to (x2, y2), deck mm."""
        self._check_xy(x1, y1)
        self._check_xy(x2, y2)
        self._gcode("TOOLS_UP")
        self._gcode("FINGER_SWIPE", X1=x1, Y1=y1, X2=x2, Y2=y2, T=int(duration_s * 1000))
        self._wait_idle()

    def finger_long_press(self, x: float, y: float, duration_s: float = 1.0) -> None:
        """Press and hold the touchscreen at deck mm (x, y)."""
        self._check_xy(x, y)
        self._gcode("TOOLS_UP")
        self._gcode("FINGER_LONG_PRESS", X=x, Y=y, T=int(duration_s * 1000))
        self._wait_idle()

    def button_press(self, name: str) -> None:
        """Press a physical side button via its servo plunger."""
        if self.device is None:
            raise HarnessError("button_press requires a device profile")
        button = self.device.buttons.get(name)
        if button is None:
            known = ", ".join(sorted(self.device.buttons)) or "<none>"
            raise HarnessError(f"device {self.device.name!r} has no button named {name!r} (known: {known})")
        self._gcode("TOOLS_UP")
        self._gcode("BUTTON_PRESS", PLUNGER=button.plunger)
        self._wait_idle()
