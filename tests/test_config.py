"""Harness config: deck-marker defaults, custom markers, validation."""

from __future__ import annotations

import pytest

from androidtester.config import ConfigError, HarnessConfig


def test_default_deck_markers_track_deck_size():
    markers = HarnessConfig(deck_width_mm=400.0, deck_height_mm=250.0).deck_marker_map()
    assert markers == {1: (20.0, 20.0), 2: (380.0, 20.0), 3: (380.0, 230.0), 4: (20.0, 230.0)}


def test_custom_deck_markers():
    cfg = HarnessConfig.from_dict({"deck_markers": {11: [10.0, 12.5], 12: [290.0, 12.5]}})
    assert cfg.deck_marker_map() == {11: (10.0, 12.5), 12: (290.0, 12.5)}


def test_bad_deck_marker_rejected():
    with pytest.raises(ConfigError, match="deck_markers"):
        HarnessConfig.from_dict({"deck_markers": {1: [10.0]}})
    with pytest.raises(ConfigError, match="marker_size_mm"):
        HarnessConfig.from_dict({"marker_size_mm": 0})
