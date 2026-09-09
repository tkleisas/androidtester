"""M0 design-package consistency: cfg <-> config.py <-> CAD <-> BOM.

These tests exist to keep the published hardware docs honest:

- the Klipper cfg's ``position_max`` values must equal the framework's deck
  defaults (a device profile trusting one side and motion trusting the other
  is how screens get cracked),
- the clearance/contact planes must match between cfg macros and config.py,
- the OpenSCAD rail constants must physically cover travel + carriage +
  margins (the arithmetic is in 00_config.scad's comments),
- the BOM table must add up: every row's qty x unit equals its line total,
  and the rows sum to the stated total.

The Klipper macro contract itself is guarded by test_macro_contract.py.
"""

from __future__ import annotations

import re

from conftest import KLIPPER_CFG, REPO_ROOT

from androidtester.config import HarnessConfig

SCAD_CONFIG = REPO_ROOT / "cad" / "openscad" / "00_config.scad"
BOM_MD = REPO_ROOT / "docs" / "03-bom.md"

SECTION = re.compile(r"^\[(\S[^]]*)\]\n(.*?)(?=^\[|\Z)", re.MULTILINE | re.DOTALL)
OPTION = re.compile(r"^(\w[\w ]*?):\s*([^\s#]+)", re.MULTILINE)
SCAD_CONST = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*([\d.]+);", re.MULTILINE)


def cfg_options(section_name: str) -> dict[str, str]:
    text = KLIPPER_CFG.read_text(encoding="utf-8")
    sections = dict(SECTION.findall(text))
    assert section_name in sections, f"cfg is missing [{section_name}]"
    return dict(OPTION.findall(sections[section_name]))


def scad_constants() -> dict[str, float]:
    text = SCAD_CONFIG.read_text(encoding="utf-8")
    consts = {name: float(value) for name, value in SCAD_CONST.findall(text)}
    assert consts, f"no constants parsed from {SCAD_CONFIG} — is the regex stale?"
    return consts


def test_position_max_matches_deck_defaults():
    defaults = HarnessConfig()
    assert float(cfg_options("stepper_x")["position_max"]) == defaults.deck_width_mm
    assert float(cfg_options("stepper_y")["position_max"]) == defaults.deck_height_mm


def test_travel_planes_match_config_defaults():
    defaults = HarnessConfig()
    at_vars = cfg_options("gcode_macro _AT_VARS")
    assert float(at_vars["variable_travel_z"]) == defaults.travel_z_mm
    assert float(at_vars["variable_touch_z"]) == defaults.touch_z_mm


def test_scad_constants_match_config_defaults():
    defaults = HarnessConfig()
    c = scad_constants()
    assert c["DECK_W"] == defaults.deck_width_mm
    assert c["DECK_D"] == defaults.deck_height_mm
    assert c["X_TRAVEL"] == defaults.deck_width_mm
    assert c["Y_TRAVEL"] == defaults.deck_height_mm
    assert c["TRAVEL_Z"] == defaults.travel_z_mm
    assert c["TOUCH_Z"] == defaults.touch_z_mm


def test_rail_lengths_cover_travel_carriage_margins():
    c = scad_constants()
    # rail >= travel + carriage + margins at both ends (00_config.scad header)
    assert c["RAIL_X_LEN"] >= c["X_TRAVEL"] + c["X_CARRIAGE_LEN"] + 2 * c["END_MARGIN"]
    assert c["RAIL_Y_LEN"] >= c["Y_TRAVEL"] + c["X_CARRIAGE_LEN"] + 2 * c["END_MARGIN"]
    assert c["RAIL_Z_LEN"] >= c["Z_TRAVEL"] + c["Z_CARRIAGE_LEN"] + 2 * c["END_MARGIN"]
    # tool-Z travel constant matches the cfg's macro variable
    assert c["Z_TRAVEL"] == float(cfg_options("gcode_macro _AT_VARS")["variable_z_top"])


def _bom_rows() -> list[tuple[str, float, float, float]]:
    rows = []
    for line in BOM_MD.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")]
        # table row: | # | item | spec | qty | unit | line | -> 8 cells
        if len(cells) != 8 or not cells[1].isdigit():
            continue
        rows.append((cells[2], float(cells[4]), float(cells[5]), float(cells[6])))
    assert rows, "no BOM rows parsed — did the table format change?"
    return rows


def test_bom_row_arithmetic():
    for item, qty, unit, line in _bom_rows():
        assert abs(qty * unit - line) < 0.01, f"BOM row '{item}': {qty} x {unit} != {line}"


def test_bom_total_matches_row_sum():
    rows = _bom_rows()
    row_sum = sum(line for _, _, _, line in rows)
    text = BOM_MD.read_text(encoding="utf-8")
    match = re.search(r"\*\*Total:\s*≈\s*€([\d.]+)\*\*", text)
    assert match, "BOM must state its total as '**Total: ≈ €X**'"
    stated = float(match.group(1))
    assert abs(stated - row_sum) < 0.01, f"stated total €{stated} != row sum €{row_sum:.2f}"
