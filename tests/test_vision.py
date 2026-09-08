"""Vision: rectification, template matching, text fallback, wait_for."""

from __future__ import annotations

import numpy as np
import pytest

from androidtester import vision
from androidtester.vision import (
    VisionError,
    VisionTimeout,
    assert_image,
    assert_text,
    rectify_screen,
    render_text_template,
    wait_for,
)


def screen_with_text(text: str, size: tuple[int, int] = (720, 1280)) -> np.ndarray:
    """A synthetic rectified screen: white text on black, like OCR would see."""
    import cv2

    image = np.zeros((size[1], size[0]), dtype=np.uint8)
    cv2.putText(image, text, (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 2.0, 255, 3, cv2.LINE_AA)
    return image


def test_rectify_screen_maps_polygon_to_rectangle():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    polygon = ((100, 50), (500, 60), (510, 400), (90, 390))
    out = rectify_screen(frame, polygon, out_width=200, out_height=300)
    assert out.shape == (300, 200, 3)


def test_rectify_screen_rejects_bad_polygon():
    with pytest.raises(VisionError, match="4 corners"):
        rectify_screen(np.zeros((10, 10, 3), dtype=np.uint8), ((0, 0), (1, 1)))


def test_assert_image_finds_template():
    screen = screen_with_text("Home")
    template = render_text_template("Home")
    score = assert_image(screen, template, threshold=0.7)
    assert score >= 0.7


def test_assert_image_rejects_absent_template():
    screen = screen_with_text("Home")
    template = render_text_template("Settings")
    with pytest.raises(VisionError, match="template not found"):
        assert_image(screen, template, threshold=0.9)


def test_assert_text_template_fallback():
    screen = screen_with_text("Home")
    assert_text(screen, "Home")  # no OCR backend: putText template match
    with pytest.raises(VisionError):
        assert_text(screen, "Volume")


class StubOCR:
    def __init__(self, text: str):
        self.text = text

    def read_text(self, image: np.ndarray) -> str:
        return self.text


def test_assert_text_with_ocr_backend():
    assert_text(np.zeros((10, 10), dtype=np.uint8), "home", ocr=StubOCR("Home screen"))
    with pytest.raises(VisionError, match="OCR saw"):
        assert_text(np.zeros((10, 10), dtype=np.uint8), "Settings", ocr=StubOCR("Home screen"))


def test_assert_text_rejects_empty_expected():
    with pytest.raises(VisionError, match="non-empty"):
        assert_text(np.zeros((10, 10), dtype=np.uint8), "")


def test_wait_for_returns_first_truthy_result():
    calls = iter([None, None, "found"])
    assert wait_for(lambda: next(calls), timeout_s=2.0, poll_s=0.001) == "found"


def test_wait_for_times_out_with_last_failure():
    def never():
        raise VisionError("text not found")

    with pytest.raises(VisionTimeout, match="text not found"):
        wait_for(never, timeout_s=0.05, poll_s=0.01)


def test_wait_for_propagates_non_vision_errors():
    def broken_camera():
        raise RuntimeError("camera unplugged")

    with pytest.raises(RuntimeError, match="camera unplugged"):
        wait_for(broken_camera, timeout_s=1.0, poll_s=0.01)
