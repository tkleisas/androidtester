"""Drift guard: every Klipper macro the framework calls must exist in the cfg.

The macro contract is `firmware/klipper/androidtester.cfg`. This test extracts
the macro names actually used in `androidtester/harness.py` (UPPER_CASE string
literals) and asserts each is defined as a `[gcode_macro ...]` there — so a
rename on either side fails CI instead of failing on the machine.
"""

from __future__ import annotations

import re

from conftest import KLIPPER_CFG, REPO_ROOT

HARNESS_PY = REPO_ROOT / "androidtester" / "harness.py"

# Macro invocations in harness.py look like _gcode("FINGER_TAP", ...) or
# run_gcode_script("PARK"); catch every bare UPPER_CASE literal.
MACRO_LITERAL = re.compile(r'"([A-Z][A-Z0-9_]{2,})"')
CFG_MACRO = re.compile(r"^\[gcode_macro (\S+)\]", re.MULTILINE)


def macros_used_by_framework() -> set[str]:
    return set(MACRO_LITERAL.findall(HARNESS_PY.read_text(encoding="utf-8")))


def macros_defined_in_cfg() -> set[str]:
    return set(CFG_MACRO.findall(KLIPPER_CFG.read_text(encoding="utf-8")))


def test_contract_macros_are_defined():
    used = macros_used_by_framework()
    assert used, "drift guard found no macros in harness.py — is the regex stale?"
    defined = macros_defined_in_cfg()
    missing = used - defined
    assert not missing, (
        f"macros used in harness.py but missing from {KLIPPER_CFG.name}: {sorted(missing)}"
    )


def test_expected_macro_set_is_present():
    # The full documented contract; guards against the regex going blind.
    expected = {"HOME_ALL", "TOOLS_UP", "FINGER_TAP", "FINGER_SWIPE", "FINGER_LONG_PRESS", "BUTTON_PRESS", "PARK"}
    assert expected <= macros_defined_in_cfg()
