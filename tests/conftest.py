"""Shared fixtures: repo paths, fake motion client, synthetic camera."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from androidtester.config import HarnessConfig
from androidtester.motion import FakeMoonrakerClient

REPO_ROOT = Path(__file__).resolve().parent.parent
DEVICES_DIR = REPO_ROOT / "devices"
SCENARIOS_DIR = REPO_ROOT / "scenarios"
KLIPPER_CFG = REPO_ROOT / "firmware" / "klipper" / "androidtester.cfg"


class StaticCamera:
    """Camera test double: always returns the same frame."""

    def __init__(self, frame: np.ndarray):
        self.frame = frame
        self.grabs = 0

    def grab(self) -> np.ndarray:
        self.grabs += 1
        return self.frame


@pytest.fixture
def fake_client() -> FakeMoonrakerClient:
    return FakeMoonrakerClient()


@pytest.fixture
def config() -> HarnessConfig:
    return HarnessConfig()
