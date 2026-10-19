"""The shared pip-audit action, run with a stand-in for uvx.

The stand-in records how pip-audit would be called and which versions each
call gets. It fails a call whose file pins a package named bad, so the tests
need no network and no real vulnerability.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the action runs in bash")

ROOT = Path(__file__).resolve().parent.parent
ACTION = yaml.safe_load(
    (ROOT / "actions" / "python" / "pip-audit" / "action.yml").read_text("utf-8")
)
(STEP,) = ACTION["runs"]["steps"]

FAKE_UVX = r"""#!/bin/bash
echo "CALL $*" >> "$UVX_LOG"
file="${@: -1}"
sed 's/^/PIN /' "$file" >> "$UVX_LOG"
if grep -q '^bad==' "$file"; then exit 1; fi
exit 0
"""


def _audit(
    tmp_path: Path, requirements: str, ignore: str = "", with_uvx: bool = True
) -> tuple[int, str, list[list[str]]]:
    """Run the action's script. Returns the exit code, the output, and for
    every pip-audit call its arguments followed by the pins it got."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if with_uvx:
        uvx = bin_dir / "uvx"
        uvx.write_text(FAKE_UVX)
        uvx.chmod(0o755)
    script = tmp_path / "audit.sh"
    script.write_text(STEP["run"])
    req = tmp_path / "versions.txt"
    req.write_text(requirements)
    log = tmp_path / "uvx.log"
    log.touch()
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "UVX_LOG": str(log),
        "REQUIREMENTS": str(req),
        "IGNORE_VULNS": ignore,
        "PIP_AUDIT_VERSION": STEP["env"]["PIP_AUDIT_VERSION"],
    }
    done = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, check=False
    )
    calls: list[list[str]] = []
    for line in log.read_text().splitlines():
        if line.startswith("CALL "):
            calls.append([line[5:]])
        else:
            calls[-1].append(line[4:])
    return done.returncode, done.stdout + done.stderr, calls


def test_every_pin_is_audited_against_pypi_and_osv(tmp_path):
    code, _, calls = _audit(tmp_path, "idna==3.15\nrequests==2.33.1\n")
    assert code == 0
    assert [c[0].split("--vulnerability-service ")[1].split()[0] for c in calls] == [
        "pypi",
        "osv",
    ]
    for call in calls:
        assert f"pip-audit=={STEP['env']['PIP_AUDIT_VERSION']}" in call[0]
        assert "--strict --no-deps --disable-pip" in call[0]
        assert call[1:] == ["idna==3.15", "requests==2.33.1"]


def test_markers_are_dropped_and_a_second_version_goes_into_its_own_call(tmp_path):
    """A lockfile pins one package in two versions for different Pythons."""
    code, _, calls = _audit(
        tmp_path,
        "idna==3.15 ; python_full_version >= '3.11'\n"
        "idna==3.7 ; python_full_version < '3.11'\n"
        "    # via requests\n",
    )
    assert code == 0
    assert sorted(c[1:] for c in calls) == [
        ["idna==3.15"],
        ["idna==3.15"],
        ["idna==3.7"],
        ["idna==3.7"],
    ]


def test_a_package_without_a_pinned_version_is_named(tmp_path):
    code, out, calls = _audit(
        tmp_path, "idna==3.15\nsomepkg @ git+https://example.invalid/somepkg@abc\n"
    )
    assert code == 0
    assert "::warning::Not audited, no pinned version: somepkg @ git+" in out
    assert all(c[1:] == ["idna==3.15"] for c in calls)


def test_each_waiver_reaches_pip_audit(tmp_path):
    _, _, calls = _audit(tmp_path, "idna==3.15\n", ignore="GHSA-aaaa-bbbb-cccc PYSEC-2026-1")
    for call in calls:
        assert "--ignore-vuln GHSA-aaaa-bbbb-cccc --ignore-vuln PYSEC-2026-1" in call[0]


def test_a_finding_fails_the_audit_after_every_call(tmp_path):
    code, _, calls = _audit(tmp_path, "bad==1.0\n")
    assert code == 1 and len(calls) == 2


@pytest.mark.parametrize("requirements", ["", "# only a comment\n"])
def test_nothing_to_audit_is_an_error(tmp_path, requirements):
    code, out, calls = _audit(tmp_path, requirements)
    assert code == 1 and calls == []
    assert "::error::" in out


def test_without_uv_the_action_says_so(tmp_path):
    if os.path.exists("/usr/bin/uvx") or os.path.exists("/bin/uvx"):
        pytest.skip("uvx is installed system-wide here")
    code, out, _ = _audit(tmp_path, "idna==3.15\n", with_uvx=False)
    assert code == 1
    assert "needs uv" in out
