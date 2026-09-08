"""Vision: screen rectification, OCR hook with template fallback, image checks.

The camera sees the device at an angle; `rectify_screen` warps the profile's
screen polygon to a flat rectangle so checks run on canonical pixels. Text
verification goes through a pluggable `OCRBackend`; when none is configured,
a template-matching fallback renders the expected text with `cv2.putText` and
matches it against the screen (the textbook approach — good enough for the
large, high-contrast UI text this machine reads).
"""

from __future__ import annotations

import time
from typing import Callable, Protocol, TypeVar, runtime_checkable

import cv2
import numpy as np


class VisionError(AssertionError):
    """Raised when a screen check fails."""


class VisionTimeout(VisionError):
    """Raised when a wait_for condition is not met before the deadline."""


@runtime_checkable
class Camera(Protocol):
    def grab(self) -> np.ndarray:
        """Return one BGR frame."""
        ...


@runtime_checkable
class OCRBackend(Protocol):
    def read_text(self, image: np.ndarray) -> str:
        """Return all text recognized in a rectified screen image."""
        ...


def rectify_screen(
    image: np.ndarray,
    polygon: tuple[tuple[float, float], ...] | np.ndarray,
    *,
    out_width: int = 720,
    out_height: int = 1280,
) -> np.ndarray:
    """Warp the screen quadrilateral (TL, TR, BR, BL, image px) to a rectangle."""
    src = np.asarray(polygon, dtype=np.float32)
    if src.shape != (4, 2):
        raise VisionError(f"screen polygon must have 4 corners, got shape {src.shape}")
    dst = np.array(
        [[0, 0], [out_width - 1, 0], [out_width - 1, out_height - 1], [0, out_height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, matrix, (out_width, out_height))


def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image


def assert_image(screen: np.ndarray, template: np.ndarray, *, threshold: float = 0.85) -> float:
    """Assert `template` appears somewhere on the rectified screen.

    Normalized cross-correlation; returns the best score for reporting.
    """
    screen_gray, template_gray = _gray(screen), _gray(template)
    if template_gray.shape[0] > screen_gray.shape[0] or template_gray.shape[1] > screen_gray.shape[1]:
        raise VisionError(
            f"template {template_gray.shape} is larger than the screen image {screen_gray.shape}"
        )
    score = float(cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED).max())
    if score < threshold:
        raise VisionError(f"template not found on screen (best match {score:.3f} < {threshold})")
    return score


def render_text_template(text: str, *, scale: float = 2.0, thickness: int = 3) -> np.ndarray:
    """Render text as a white-on-black template image (putText-based)."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    (width, height), baseline = cv2.getTextSize(text, font, scale, thickness)
    template = np.zeros((height + baseline + 8, width + 8), dtype=np.uint8)
    cv2.putText(template, text, (4, height + 2), font, scale, 255, thickness, cv2.LINE_AA)
    return template


def assert_text(
    screen: np.ndarray,
    expected: str,
    *,
    ocr: OCRBackend | None = None,
    threshold: float = 0.7,
) -> str:
    """Assert `expected` text is visible on the rectified screen.

    With an OCR backend: substring match on the recognized text (case-folded).
    Without one: template-match the rendered text against the screen.
    """
    if not expected:
        raise VisionError("expected text must be non-empty")
    if ocr is not None:
        found = ocr.read_text(screen)
        if expected.casefold() not in found.casefold():
            raise VisionError(f"text {expected!r} not found on screen (OCR saw {found!r})")
        return found
    score = assert_image(screen, render_text_template(expected), threshold=threshold)
    return f"template match {score:.3f}"


T = TypeVar("T")


def wait_for(
    check: Callable[[], T | None],
    *,
    timeout_s: float,
    poll_s: float = 0.5,
    description: str = "condition",
) -> T:
    """Poll `check` until it returns a truthy value; raise VisionTimeout otherwise.

    Check failures that raise VisionError count as "not yet"; anything else
    propagates (a broken camera must not look like a slow screen).
    """
    deadline = time.monotonic() + timeout_s
    last_error: VisionError | None = None
    while True:
        try:
            result = check()
            if result:
                return result
        except VisionError as exc:
            last_error = exc
        if time.monotonic() >= deadline:
            detail = f" (last failure: {last_error})" if last_error else ""
            raise VisionTimeout(f"{description} not met within {timeout_s}s{detail}")
        time.sleep(poll_s)
