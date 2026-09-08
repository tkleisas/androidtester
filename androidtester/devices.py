"""Device profiles (`devices/*.yaml`): geometry the machine needs to touch a DUT.

A profile describes one device class member in deck millimetres: body size,
the screen quadrilateral (corners ordered TL, TR, BR, BL), the physical side
buttons mapped to servo plungers, launcher/pin-pad touch points in
screen-relative fractions, and a free-form quirks dict. New device = new YAML,
not new code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

DeviceClass = Literal["phone", "tablet"]
DEVICE_CLASSES: tuple[str, ...] = ("phone", "tablet")


class ProfileValidationError(ValueError):
    """Raised when a device profile is invalid; the message names the field."""


@dataclass(frozen=True)
class Button:
    """A physical side button and the servo plunger that presses it."""

    name: str
    position: tuple[float, float, float]  # deck mm (x, y, z of the button face)
    plunger: str


@dataclass(frozen=True)
class LauncherEntry:
    """A named touch point in screen-relative fractions (0..1, origin top-left)."""

    name: str
    x: float
    y: float


@dataclass(frozen=True)
class DeviceProfile:
    name: str
    device_class: DeviceClass
    body_width_mm: float
    body_height_mm: float
    body_thickness_mm: float
    screen_polygon: tuple[tuple[float, float], ...]  # 4 deck-mm corners: TL, TR, BR, BL
    buttons: dict[str, Button] = field(default_factory=dict)
    launcher: dict[str, LauncherEntry] = field(default_factory=dict)
    quirks: dict[str, Any] = field(default_factory=dict)

    def screen_point(self, fx: float, fy: float) -> tuple[float, float]:
        """Map screen-relative fractions to deck mm (bilinear over the quad)."""
        tl, tr, br, bl = self.screen_polygon
        x = (1 - fx) * (1 - fy) * tl[0] + fx * (1 - fy) * tr[0] + fx * fy * br[0] + (1 - fx) * fy * bl[0]
        y = (1 - fx) * (1 - fy) * tl[1] + fx * (1 - fy) * tr[1] + fx * fy * br[1] + (1 - fx) * fy * bl[1]
        return (x, y)


def _err(source: str, message: str) -> ProfileValidationError:
    return ProfileValidationError(f"{source}: {message}")


def _require_number(source: str, field_name: str, value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _err(source, f"field {field_name!r} must be a number, got {value!r}")
    if positive and value <= 0:
        raise _err(source, f"field {field_name!r} must be positive, got {value!r}")
    return float(value)


def _parse_button(source: str, name: str, data: Any) -> Button:
    if not isinstance(data, dict):
        raise _err(source, f"field 'buttons.{name}' must be a mapping, got {type(data).__name__}")
    pos = data.get("position")
    if not isinstance(pos, (list, tuple)) or len(pos) != 3:
        raise _err(source, f"field 'buttons.{name}.position' must be [x, y, z] in deck mm, got {pos!r}")
    xyz = tuple(
        _require_number(source, f"buttons.{name}.position[{i}]", v) for i, v in enumerate(pos)
    )
    plunger = data.get("plunger")
    if not isinstance(plunger, str) or not plunger:
        raise _err(source, f"field 'buttons.{name}.plunger' must be a non-empty string, got {plunger!r}")
    return Button(name=name, position=xyz, plunger=plunger)


def _parse_launcher_entry(source: str, name: str, data: Any) -> LauncherEntry:
    if not isinstance(data, dict):
        raise _err(source, f"field 'launcher.{name}' must be a mapping, got {type(data).__name__}")
    x = _require_number(source, f"launcher.{name}.x", data.get("x"))
    y = _require_number(source, f"launcher.{name}.y", data.get("y"))
    if not (0.0 <= x <= 1.0) or not (0.0 <= y <= 1.0):
        raise _err(source, f"field 'launcher.{name}' fractions must be within 0..1, got x={x}, y={y}")
    return LauncherEntry(name=name, x=x, y=y)


def profile_from_dict(data: dict[str, Any], *, source: str = "<dict>") -> DeviceProfile:
    if not isinstance(data, dict):
        raise _err(source, f"top level must be a mapping, got {type(data).__name__}")

    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise _err(source, f"field 'name' must be a non-empty string, got {name!r}")

    device_class = data.get("class")
    if device_class not in DEVICE_CLASSES:
        raise _err(source, f"field 'class' must be one of {DEVICE_CLASSES}, got {device_class!r}")

    body = data.get("body")
    if not isinstance(body, dict):
        raise _err(source, "field 'body' must be a mapping with width_mm/height_mm/thickness_mm")
    width = _require_number(source, "body.width_mm", body.get("width_mm"), positive=True)
    height = _require_number(source, "body.height_mm", body.get("height_mm"), positive=True)
    thickness = _require_number(source, "body.thickness_mm", body.get("thickness_mm"), positive=True)

    polygon_raw = data.get("screen_polygon")
    if not isinstance(polygon_raw, (list, tuple)) or len(polygon_raw) != 4:
        raise _err(source, f"field 'screen_polygon' must have exactly 4 corner points, got {polygon_raw!r}")
    polygon: list[tuple[float, float]] = []
    for i, point in enumerate(polygon_raw):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise _err(source, f"field 'screen_polygon[{i}]' must be [x, y], got {point!r}")
        polygon.append(
            (
                _require_number(source, f"screen_polygon[{i}][0]", point[0]),
                _require_number(source, f"screen_polygon[{i}][1]", point[1]),
            )
        )

    buttons_raw = data.get("buttons", {})
    if not isinstance(buttons_raw, dict):
        raise _err(source, "field 'buttons' must be a mapping of name -> {position, plunger}")
    buttons = {str(k): _parse_button(source, str(k), v) for k, v in buttons_raw.items()}

    launcher_raw = data.get("launcher", {})
    if not isinstance(launcher_raw, dict):
        raise _err(source, "field 'launcher' must be a mapping of name -> {x, y}")
    launcher = {str(k): _parse_launcher_entry(source, str(k), v) for k, v in launcher_raw.items()}

    quirks = data.get("quirks", {})
    if not isinstance(quirks, dict):
        raise _err(source, "field 'quirks' must be a mapping")

    return DeviceProfile(
        name=name,
        device_class=device_class,  # type: ignore[arg-type]
        body_width_mm=width,
        body_height_mm=height,
        body_thickness_mm=thickness,
        screen_polygon=tuple(polygon),
        buttons=buttons,
        launcher=launcher,
        quirks=dict(quirks),
    )


def load_profile(path: str | Path) -> DeviceProfile:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileValidationError(f"cannot read device profile {path}: {exc}") from exc
    return profile_from_dict(data, source=str(path))


def load_profile_by_name(name: str, devices_dir: str | Path) -> DeviceProfile:
    path = Path(devices_dir) / f"{name}.yaml"
    if not path.is_file():
        raise ProfileValidationError(f"no device profile named {name!r} in {devices_dir}")
    return load_profile(path)
