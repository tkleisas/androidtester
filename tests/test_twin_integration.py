"""M4 twin parity: the unmodified framework against the Steropes twin.

Skipped by default. To enable, point STEROPES_ROOT at a steropes checkout
that has a built venv (Git Bash: `STEROPES_ROOT=/c/projects/steropes`), then
run pytest normally. Two guards:

- macro drift: every macro name `androidtester.harness` emits must be
  dispatched by the twin's `steropes/server.py` (parsed, not run — cheap);
- end-to-end: the twin server is spawned on an ephemeral port and
  `scenarios/smoke_wake_unlock.yaml` runs against it through the real
  runner — HTTP motion, MJPEG camera, ArUco calibration, vision checks.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests
import yaml

from androidtester.cameras import camera_from_config
from androidtester.config import HarnessConfig
from androidtester.scenario import run_scenario_file
from conftest import DEVICES_DIR, REPO_ROOT, SCENARIOS_DIR
from test_macro_contract import MACRO_LITERAL, macros_used_by_framework

_ROOT = os.environ.get("STEROPES_ROOT")
STEROPES_ROOT = Path(_ROOT) if _ROOT else None
SERVER_PY = STEROPES_ROOT / "steropes" / "server.py" if STEROPES_ROOT else None
TWIN_PYTHON = STEROPES_ROOT / ".venv" / "Scripts" / "python.exe" if STEROPES_ROOT else None
TWIN_PROFILE = STEROPES_ROOT / "profiles" / "android_phone_v1.yaml" if STEROPES_ROOT else None

pytestmark = pytest.mark.skipif(
    not (SERVER_PY and SERVER_PY.is_file() and TWIN_PYTHON.is_file() and TWIN_PROFILE.is_file()),
    reason="set STEROPES_ROOT to a steropes checkout (with .venv) to enable twin parity tests",
)


def _macros_handled_by_twin() -> set[str]:
    """Macro names dispatched inside TwinMachine._exec_line (parsed, not run)."""
    text = SERVER_PY.read_text(encoding="utf-8")
    start = text.index("def _exec_line")
    end = text.index("\n    def ", start)  # the next TwinMachine method
    return set(MACRO_LITERAL.findall(text[start:end]))


def test_twin_handles_every_framework_macro() -> None:
    """Cross-repo drift guard: no harness macro may be unknown to the twin."""
    used = macros_used_by_framework()
    handled = _macros_handled_by_twin()
    missing = used - handled
    assert not missing, (
        f"macros used in harness.py but not dispatched by the twin's server.py: {sorted(missing)}"
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(base: str, proc: subprocess.Popen, log_path: Path, timeout_s: float = 180.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        try:
            if requests.get(f"{base}/server/info", timeout=2.0).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1.0)
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
    raise RuntimeError(f"twin server did not become ready on {base}; log tail:\n{tail}")


@pytest.fixture(scope="module")
def twin_base_url(tmp_path_factory):
    """The twin server as a subprocess on an ephemeral port; yields its base URL."""
    workdir = tmp_path_factory.mktemp("twin")
    log_path = workdir / "twin.log"
    port = _free_port()
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [
                str(TWIN_PYTHON), "-m", "steropes.server",
                "--profile", str(TWIN_PROFILE),
                "--port", str(port),
                "--workdir", str(workdir),
            ],
            cwd=str(STEROPES_ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_ready(base, proc, log_path)
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30.0)
        except subprocess.TimeoutExpired:
            proc.kill()


def _twin_config(base: str) -> HarnessConfig:
    """The shipped harness.twin.yaml, re-pointed at the ephemeral port."""
    data = yaml.safe_load((REPO_ROOT / "harness.twin.yaml").read_text(encoding="utf-8"))
    data["moonraker_url"] = base
    data["cameras"]["overhead"] = f"{base}/camera/overhead"
    return HarnessConfig.from_dict(data, source="harness.twin.yaml")


def test_smoke_scenario_passes_against_twin(twin_base_url, monkeypatch) -> None:
    """scenarios/smoke_wake_unlock.yaml end-to-end via the in-process runner."""
    pin = str(yaml.safe_load(TWIN_PROFILE.read_text(encoding="utf-8"))["pin"])
    monkeypatch.setenv("DEVICE_PIN_1", pin)  # the simulated DUT's PIN, from its profile
    config = _twin_config(twin_base_url)
    camera = camera_from_config(config)
    result = run_scenario_file(
        SCENARIOS_DIR / "smoke_wake_unlock.yaml",
        config=config,
        devices_dir=DEVICES_DIR,
        camera=camera,
    )
    failures = [f"{s.action}: {s.detail}" for s in result.steps if s.status == "failed"]
    assert result.passed, "smoke_wake_unlock failed against the twin: " + "; ".join(failures)
