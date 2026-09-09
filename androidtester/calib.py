"""Camera deck registration: ArUco markers + a px <-> deck-mm homography.

The deck carries printed ArUco markers at known deck-mm coordinates (see
``HarnessConfig.deck_markers``). `calibrate_deck` detects them in an overhead
frame, solves a normalized-DLT homography from all detected marker corners
(overdetermined: 4 corners per marker), and reports the RMS reprojection
error in millimetres. Failures are loud: a missing marker is named, and an
RMS above the requested threshold fails with the numbers.

CLI: python -m androidtester.calib [--config cfg.yaml] [--device name] [--out out]
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np


class CalibrationError(RuntimeError):
    """Raised when deck registration fails (missing markers, bad fit)."""


@dataclass(frozen=True)
class MarkerDetection:
    """One detected ArUco marker: corners TL, TR, BR, BL in image px."""

    marker_id: int
    corners: tuple[tuple[float, float], ...]

    @property
    def center(self) -> tuple[float, float]:
        xs = [c[0] for c in self.corners]
        ys = [c[1] for c in self.corners]
        return (sum(xs) / 4.0, sum(ys) / 4.0)


@dataclass(frozen=True)
class DeckCalibration:
    """A solved px <-> deck-mm mapping plus its fit quality."""

    homography: np.ndarray  # 3x3, image px -> deck mm
    rms_mm: float
    detections: tuple[MarkerDetection, ...]

    def px_to_deck(self, u: float, v: float) -> tuple[float, float]:
        """Map one image pixel to deck mm."""
        p = self.homography @ np.array([u, v, 1.0])
        return (float(p[0] / p[2]), float(p[1] / p[2]))

    def deck_point(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        """Inverse map: deck mm -> image pixel (debugging/annotation)."""
        p = np.linalg.inv(self.homography) @ np.array([x_mm, y_mm, 1.0])
        return (float(p[0] / p[2]), float(p[1] / p[2]))

    def screen_polygon_px(self, polygon_mm: Sequence[Sequence[float]]) -> np.ndarray:
        """Screen corners (deck mm, TL TR BR BL) mapped into image px."""
        return np.array([self.deck_point(x, y) for x, y in polygon_mm], dtype=np.float32)


def _aruco_dictionary():
    """DICT_4X4_50 across opencv 4.x/5.x API shapes."""
    aruco = cv2.aruco
    code = aruco.DICT_4X4_50
    if hasattr(aruco, "getPredefinedDictionary"):
        return aruco.getPredefinedDictionary(code)
    return aruco.Dictionary_get(code)  # opencv < 4.7


def detect_markers(frame: np.ndarray) -> list[MarkerDetection]:
    """Detect ArUco markers in one BGR frame (version-tolerant)."""
    aruco = cv2.aruco
    dictionary = _aruco_dictionary()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    if hasattr(aruco, "ArucoDetector"):  # opencv >= 4.7 / 5.x
        detector = aruco.ArucoDetector(dictionary, aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(gray)
    else:  # opencv < 4.7
        corners, ids, _ = aruco.detectMarkers(gray, dictionary)
    if ids is None:
        return []
    return [
        MarkerDetection(int(marker_id), tuple((float(p[0]), float(p[1])) for p in quad.reshape(4, 2)))
        for quad, marker_id in zip(corners, ids.flatten())
    ]


def _normalization_matrix(points: np.ndarray) -> np.ndarray:
    """Translate to centroid and scale so mean distance to origin is sqrt(2)."""
    centroid = points.mean(axis=0)
    scale = np.sqrt(2.0) / max(np.linalg.norm(points - centroid, axis=1).mean(), 1e-12)
    return np.array(
        [[scale, 0.0, -scale * centroid[0]], [0.0, scale, -scale * centroid[1]], [0.0, 0.0, 1.0]]
    )


def solve_homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Normalized DLT homography mapping src points (N,2) onto dst (N,2), N >= 4."""
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    if src.shape != dst.shape or src.ndim != 2 or src.shape[1] != 2 or src.shape[0] < 4:
        raise CalibrationError(f"need >= 4 corresponding point pairs, got shapes {src.shape} / {dst.shape}")
    t_src, t_dst = _normalization_matrix(src), _normalization_matrix(dst)
    src_n = (t_src @ np.hstack([src, np.ones((len(src), 1))]).T).T
    dst_n = (t_dst @ np.hstack([dst, np.ones((len(dst), 1))]).T).T
    rows = []
    for (x, y, _), (u, v, _) in zip(src_n, dst_n):
        rows.append([-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u])
        rows.append([0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v])
    _, _, vt = np.linalg.svd(np.array(rows))
    h_norm = vt[-1].reshape(3, 3)
    h = np.linalg.inv(t_dst) @ h_norm @ t_src
    return h / h[2, 2]


def _marker_deck_corners(center_mm: tuple[float, float], size_mm: float) -> list[tuple[float, float]]:
    """Deck-mm corners in ArUco's reported order (pattern TL, TR, BR, BL).

    Convention: the marker is printed as ``generateImageMarker`` renders it
    and placed face-up with pattern corner 0 (top-left of the printed image)
    toward the deck's (+x, -y) side. The mapping is validated by detection:
    any orientation flip here mirrors the pattern and detection fails.
    """
    cx, cy = center_mm
    h = size_mm / 2.0
    return [(cx + h, cy - h), (cx - h, cy - h), (cx - h, cy + h), (cx + h, cy + h)]


def calibrate_deck(
    frame: np.ndarray,
    markers: Mapping[int, tuple[float, float]],
    *,
    marker_size_mm: float = 20.0,
    rms_below_mm: float | None = None,
) -> DeckCalibration:
    """Register the deck: detect the configured markers, solve px -> deck mm.

    Every configured marker must be visible; `rms_below_mm` (when given) is a
    hard gate on the fit quality.
    """
    detections = {d.marker_id: d for d in detect_markers(frame)}
    missing = [marker_id for marker_id in markers if marker_id not in detections]
    if missing:
        found = sorted(detections) or ["<none>"]
        raise CalibrationError(
            f"deck marker(s) {missing} not visible in the frame (detected ids: {found}); "
            "check marker placement and lighting"
        )
    px_points: list[tuple[float, float]] = []
    mm_points: list[tuple[float, float]] = []
    used = [detections[marker_id] for marker_id in sorted(markers)]
    for detection in used:
        px_points.extend(detection.corners)
        mm_points.extend(_marker_deck_corners(markers[detection.marker_id], marker_size_mm))
    homography = solve_homography(np.array(px_points), np.array(mm_points))
    calibration = DeckCalibration(homography, rms_mm=0.0, detections=tuple(used))
    errors = [
        np.linalg.norm(np.array(calibration.px_to_deck(u, v)) - np.array(mm))
        for (u, v), mm in zip(px_points, mm_points)
    ]
    rms = float(np.sqrt(np.mean(np.square(errors))))
    calibration = DeckCalibration(homography, rms_mm=rms, detections=tuple(used))
    if rms_below_mm is not None and rms > rms_below_mm:
        raise CalibrationError(
            f"deck calibration RMS {rms:.3f} mm exceeds the {rms_below_mm} mm threshold "
            f"({len(used)} markers, {len(px_points)} corners); re-seat markers and retry"
        )
    return calibration


def annotate_frame(
    frame: np.ndarray,
    calibration: DeckCalibration,
    *,
    screen_polygon_mm: Sequence[Sequence[float]] | None = None,
    grid_step_mm: float = 50.0,
) -> np.ndarray:
    """Draw detections, the reprojected deck grid, and the screen quad."""
    out = frame.copy()
    for detection in calibration.detections:
        quad = np.array(detection.corners, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [quad], True, (0, 255, 0), 2)
        cx, cy = (int(v) for v in detection.center)
        cv2.putText(
            out, f"id {detection.marker_id}", (cx - 20, cy - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA,
        )
    max_x = max(x for d in calibration.detections for x, _ in d.corners)
    max_y = max(y for d in calibration.detections for _, y in d.corners)
    max_mm = max(
        calibration.px_to_deck(max_x, max_y)[0],
        calibration.px_to_deck(max_x, max_y)[1],
    )
    step = grid_step_mm
    for i in range(0, int(max_mm // step) + 2):
        for p0, p1 in (((i * step, 0.0), (i * step, max_mm)), ((0.0, i * step), (max_mm, i * step))):
            a = tuple(int(v) for v in calibration.deck_point(*p0))
            b = tuple(int(v) for v in calibration.deck_point(*p1))
            cv2.line(out, a, b, (255, 180, 0), 1)
    if screen_polygon_mm is not None:
        quad = calibration.screen_polygon_px(screen_polygon_mm).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [quad], True, (0, 0, 255), 2)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="androidtester.calib",
        description="Register the overhead camera to the deck via ArUco markers.",
    )
    parser.add_argument("--config", help="harness config YAML (defaults applied otherwise)")
    parser.add_argument("--devices", default="devices", help="device profiles directory")
    parser.add_argument("--device", help="device profile name (adds the screen quad overlay)")
    parser.add_argument("--rms-below-mm", type=float, default=None, help="hard gate on fit RMS")
    parser.add_argument("--out", default="out", help="artifact output directory")
    args = parser.parse_args(argv)

    from . import cameras
    from .config import HarnessConfig
    from .devices import load_profile_by_name

    config = HarnessConfig.load(args.config) if args.config else HarnessConfig()
    profile = load_profile_by_name(args.device, args.devices) if args.device else None
    camera = cameras.camera_from_config(config, profile)
    frame = camera.grab()
    markers = config.deck_marker_map()
    try:
        calibration = calibrate_deck(
            frame, markers, marker_size_mm=config.marker_size_mm, rms_below_mm=args.rms_below_mm
        )
    except CalibrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"detected {len(calibration.detections)} deck markers:")
    for detection in calibration.detections:
        expected = markers[detection.marker_id]
        actual = calibration.px_to_deck(*detection.center)
        err = float(np.hypot(actual[0] - expected[0], actual[1] - expected[1]))
        print(
            f"  id {detection.marker_id}: px center ({detection.center[0]:.1f}, "
            f"{detection.center[1]:.1f}) -> deck ({actual[0]:.2f}, {actual[1]:.2f}) mm "
            f"(expected ({expected[0]:.2f}, {expected[1]:.2f}), err {err:.3f} mm)"
        )
    print(f"RMS reprojection error: {calibration.rms_mm:.3f} mm")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    annotated = annotate_frame(
        frame, calibration,
        screen_polygon_mm=profile.screen_polygon if profile else None,
    )
    path = out_dir / f"calibration_{time.strftime('%Y%m%d_%H%M%S')}.png"
    cv2.imwrite(str(path), annotated)
    print(f"annotated frame: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
