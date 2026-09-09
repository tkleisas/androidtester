"""Camera sources: an OpenCV grab and a synthetic renderer for tests/dev.

`OpenCVCamera` wraps `cv2.VideoCapture` (device index or stream URL from the
harness config). `SyntheticCamera` renders the configured deck — ArUco markers
at their config positions, the device screen quad — through a configurable
virtual pinhole pose (real perspective projection via `cv2.projectPoints`),
so the calibration math is exercised without hardware.

Selection via config: ``cameras: {overhead: synthetic}`` or an OpenCV
index/URL. ``camera_from_config`` builds the right one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Sequence, runtime_checkable

import cv2
import numpy as np

from .calib import _aruco_dictionary, _marker_deck_corners

if TYPE_CHECKING:
    from .config import HarnessConfig
    from .devices import DeviceProfile


class CameraError(RuntimeError):
    """Raised when a frame cannot be grabbed (closed device, dead stream)."""


@runtime_checkable
class OverheadCamera(Protocol):
    def grab(self) -> np.ndarray:
        """Return one BGR frame."""
        ...


class OpenCVCamera:
    """Overhead camera backed by cv2.VideoCapture; the device opens lazily."""

    def __init__(self, source: str):
        self._source: int | str = int(source) if str(source).isdigit() else source
        self._cap: cv2.VideoCapture | None = None

    def grab(self) -> np.ndarray:
        if self._cap is None:
            self._cap = cv2.VideoCapture(self._source)
            if not self._cap.isOpened():
                raise CameraError(f"cannot open camera source {self._source!r}")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise CameraError(f"grab failed from camera source {self._source!r}")
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


@dataclass(frozen=True)
class VirtualPose:
    """Pose of the synthetic camera: above `center_mm`, near-straight down.

    Tilts/yaw are small Euler angles (deg) applied on top of a straight-down
    view, so rendered markers are genuinely perspective-distorted.
    """

    height_mm: float = 420.0
    tilt_x_deg: float = 6.0
    tilt_y_deg: float = -5.0
    yaw_deg: float = 3.0
    focal_px: float = 900.0
    center_mm: tuple[float, float] | None = None  # look-at; default: deck center


def _euler_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> np.ndarray:
    """Rz(rz) @ Ry(ry) @ Rx(rx) for angles in degrees."""
    rx, ry, rz = (math.radians(a) for a in (rx_deg, ry_deg, rz_deg))
    rot_x = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    rot_y = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
    rot_z = np.array([[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]])
    return rot_z @ rot_y @ rot_x


def _warp_patch(frame: np.ndarray, patch: np.ndarray, dst_quad_px: np.ndarray) -> None:
    """Perspective-warp a flat BGR patch onto a quad inside `frame`."""
    height, width = patch.shape[:2]
    src = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst_quad_px.astype(np.float32))
    size = (frame.shape[1], frame.shape[0])
    warped = cv2.warpPerspective(patch, matrix, size)
    mask = cv2.warpPerspective(np.full((height, width), 255, dtype=np.uint8), matrix, size)
    frame[mask > 0] = warped[mask > 0]


class SyntheticCamera:
    """Renders the configured deck through a virtual pose; no hardware."""

    def __init__(
        self,
        config: HarnessConfig,
        profile: DeviceProfile | None = None,
        *,
        image_size: tuple[int, int] = (1280, 960),
        pose: VirtualPose | None = None,
        screen_text: str | None = None,
    ):
        self._config = config
        self._profile = profile
        self._image_size = image_size
        self._pose = pose or VirtualPose()
        self._screen_text = screen_text
        self._frame: np.ndarray | None = None

    # -- projection ----------------------------------------------------------

    @property
    def _projection(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(rvec, tvec, K) of the virtual camera looking at the deck plane."""
        pose = self._pose
        width, height = self._image_size
        center = pose.center_mm or (self._config.deck_width_mm / 2.0, self._config.deck_height_mm / 2.0)
        camera_mm = np.array([center[0], center[1], pose.height_mm])
        rot_down = np.diag([1.0, -1.0, -1.0])  # straight down: deck +y is image up
        rot = _euler_matrix(pose.tilt_x_deg, pose.tilt_y_deg, pose.yaw_deg) @ rot_down
        tvec = -rot @ camera_mm
        rvec = cv2.Rodrigues(rot)[0]
        intrinsic = np.array(
            [[pose.focal_px, 0.0, width / 2.0], [0.0, pose.focal_px, height / 2.0], [0.0, 0.0, 1.0]]
        )
        return rvec, tvec, intrinsic

    def project(self, points_mm: Sequence[Sequence[float]]) -> np.ndarray:
        """Ground-truth projection of deck-plane points (x, y mm) to pixels."""
        rvec, tvec, intrinsic = self._projection
        points_3d = np.array([[x, y, 0.0] for x, y in points_mm], dtype=np.float64)
        projected, _ = cv2.projectPoints(points_3d, rvec, tvec, intrinsic, None)
        return projected.reshape(-1, 2)

    # -- rendering -------------------------------------------------------------

    def _render(self) -> np.ndarray:
        width, height = self._image_size
        frame = np.full((height, width, 3), 25, dtype=np.uint8)
        deck = self._project_quad(
            [(0.0, 0.0), (self._config.deck_width_mm, 0.0),
             (self._config.deck_width_mm, self._config.deck_height_mm),
             (0.0, self._config.deck_height_mm)]
        )
        cv2.fillConvexPoly(frame, deck.astype(np.int32), (190, 190, 190))
        for marker_id, center in sorted(self._config.deck_marker_map().items()):
            self._render_marker(frame, marker_id, center)
        if self._profile is not None:
            self._render_device(frame)
        return frame

    def _project_quad(self, points_mm: Sequence[Sequence[float]]) -> np.ndarray:
        return self.project(points_mm).astype(np.float32)

    def _render_marker(self, frame: np.ndarray, marker_id: int, center_mm: tuple[float, float]) -> None:
        texture = cv2.aruco.generateImageMarker(_aruco_dictionary(), marker_id, 200)
        patch = cv2.cvtColor(texture, cv2.COLOR_GRAY2BGR)
        quad = self._project_quad(_marker_deck_corners(center_mm, self._config.marker_size_mm))
        _warp_patch(frame, patch, quad)

    def _render_device(self, frame: np.ndarray) -> None:
        profile = self._profile
        assert profile is not None
        polygon = profile.screen_polygon
        quad = self._project_quad(polygon)
        # Body rectangle centered on the screen quad, slightly darker than the deck.
        cx = sum(p[0] for p in polygon) / 4.0
        cy = sum(p[1] for p in polygon) / 4.0
        hw, hh = profile.body_width_mm / 2.0, profile.body_height_mm / 2.0
        body = self._project_quad([(cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)])
        cv2.fillConvexPoly(frame, body.astype(np.int32), (120, 120, 120))
        # Screen patch, 4 px/mm, with optional text for OCR-flavored tests.
        tl, tr, _, bl = polygon
        patch_w = max(int(round(math.hypot(tr[0] - tl[0], tr[1] - tl[1]) * 4)), 8)
        patch_h = max(int(round(math.hypot(bl[0] - tl[0], bl[1] - tl[1]) * 4)), 8)
        patch = np.full((patch_h, patch_w, 3), (60, 60, 60), dtype=np.uint8)
        if self._screen_text:
            cv2.putText(
                patch, self._screen_text, (patch_w // 10, patch_h // 6),
                cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 3, cv2.LINE_AA,
            )
        _warp_patch(frame, patch, quad)

    def grab(self) -> np.ndarray:
        """Return the rendered frame (deterministic; one render, fresh copies)."""
        if self._frame is None:
            self._frame = self._render()
        return self._frame.copy()


def camera_from_config(
    config: HarnessConfig, profile: DeviceProfile | None = None, *, name: str = "overhead"
) -> OverheadCamera:
    """Build the camera named by the config; absent config means synthetic."""
    source = config.cameras.get(name, "synthetic")
    if source == "synthetic":
        return SyntheticCamera(config, profile)
    return OpenCVCamera(source)
