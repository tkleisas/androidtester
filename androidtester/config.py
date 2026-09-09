"""Harness configuration: Moonraker endpoint, cameras, deck geometry, safety planes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when the harness config is missing or malformed."""


@dataclass(frozen=True)
class HarnessConfig:
    """Static configuration of one test rig.

    ``travel_z_mm`` is the safety clearance plane: no XY travel happens below
    it. ``touch_z_mm`` is the finger-tip contact height for the mounted device
    and must be lower than the travel plane.
    """

    moonraker_url: str = "http://localhost:7125"
    cameras: dict[str, str] = field(default_factory=dict)
    deck_width_mm: float = 300.0
    deck_height_mm: float = 300.0
    travel_z_mm: float = 40.0
    touch_z_mm: float = 5.0
    idle_timeout_s: float = 60.0
    dry_run: bool = False
    #: ArUco deck markers: id -> [x_mm, y_mm] of the marker center, printed as
    #: generateImageMarker renders them with pattern corner 0 toward (+x, -y)
    #: (see calib._marker_deck_corners). Empty -> defaults (ids 1-4, one
    #: marker-width in from each deck corner).
    deck_markers: dict[int, Any] = field(default_factory=dict)
    marker_size_mm: float = 20.0

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "<dict>") -> "HarnessConfig":
        if not isinstance(data, dict):
            raise ConfigError(f"{source}: top level must be a mapping, got {type(data).__name__}")
        known = {f for f in cls.__dataclass_fields__}  # noqa: C401
        for key in data:
            if key not in known:
                raise ConfigError(f"{source}: unknown field {key!r}")

        cfg = cls(**data)
        errors: list[str] = []
        for name in (
            "deck_width_mm", "deck_height_mm", "travel_z_mm", "touch_z_mm", "idle_timeout_s",
            "marker_size_mm",
        ):
            value = getattr(cfg, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"field {name!r} must be a positive number, got {value!r}")
        if not isinstance(cfg.moonraker_url, str) or not cfg.moonraker_url.startswith("http"):
            errors.append(f"field 'moonraker_url' must be an http(s) URL, got {cfg.moonraker_url!r}")
        if not isinstance(cfg.cameras, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in cfg.cameras.items()
        ):
            errors.append("field 'cameras' must be a mapping of name -> source (device index or URL)")
        if not isinstance(cfg.deck_markers, dict):
            errors.append("field 'deck_markers' must be a mapping of marker id -> [x_mm, y_mm]")
        else:
            for marker_id, pos in cfg.deck_markers.items():
                if isinstance(marker_id, bool) or not isinstance(marker_id, int):
                    errors.append(f"field 'deck_markers' key must be an integer marker id, got {marker_id!r}")
                elif (
                    not isinstance(pos, (list, tuple))
                    or len(pos) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in pos)
                ):
                    errors.append(f"field 'deck_markers.{marker_id}' must be [x_mm, y_mm], got {pos!r}")
        if not errors and cfg.touch_z_mm >= cfg.travel_z_mm:
            errors.append(
                f"field 'touch_z_mm' ({cfg.touch_z_mm}) must be below the "
                f"travel clearance plane 'travel_z_mm' ({cfg.travel_z_mm})"
            )
        if errors:
            raise ConfigError(f"{source}: " + "; ".join(errors))
        return cfg

    def deck_marker_map(self) -> dict[int, tuple[float, float]]:
        """Marker id -> center position in deck mm; corner defaults when unset."""
        if self.deck_markers:
            return {int(k): (float(v[0]), float(v[1])) for k, v in self.deck_markers.items()}
        inset = float(self.marker_size_mm)
        return {
            1: (inset, inset),
            2: (self.deck_width_mm - inset, inset),
            3: (self.deck_width_mm - inset, self.deck_height_mm - inset),
            4: (inset, self.deck_height_mm - inset),
        }

    @classmethod
    def load(cls, path: str | Path) -> "HarnessConfig":
        path = Path(path)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"cannot read harness config {path}: {exc}") from exc
        return cls.from_dict(data or {}, source=str(path))
