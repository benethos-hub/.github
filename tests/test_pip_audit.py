"""The shared pip-audit action, run with a stand-in for uv.

The stand-in records how pip-audit would be called and which versions each
call gets. It fails a call whose file pins a package named bad, so the tests
need no network and no real vulnerability.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the action runs in bash"
)

ROOT = Path(__file__).resolve().parent.parent
ACTION_DIR = ROOT / "actions" / "python" / "pip-audit"
ACTION = yaml.safe_load((ACTION_DIR / "action.yml").read_text("utf-8"))
UV_STEP, STEP = ACTION["runs"]["steps"]

FAKE_UV = r"""#!/bin/bash
# The call of findings.py is forwarded to the real script.
case "$*" in *findings.py) exec python3 "${@: -1}" ;; esac
echo "CALL $* ENV $UV_PROJECT_ENVIRONMENT" >> "$UV_LOG"
file="${@: -1}"
sed 's/^/PIN /' "$file" >> "$UV_LOG"
# With --output, pip-audit writes JSON and exits 1 on a vulnerability. A
# package named broken cannot be audited at all and leaves no file.
out=""
for ((i = 1; i < $#; i++)); do
  if [ "${!i}" = --output ]; then j=$((i + 1)); out="${!j}"; fi
done
if grep -q '^broken==' "$file"; then exit 1; fi
if grep -q '^bad==' "$file"; then
  if [ -n "$out" ]; then
    vulns='[{"id": "GHSA-bad0-bad0-bad0", "fix_versions": ["1.1"]}]'
    bad='{"name": "bad", "version": "1.0", "vulns": '"$vulns"'}'
    echo '{"dependencies": ['"$bad"'], "fixes": []}' > "$out"
  fi
  exit 1
fi
if [ -n "$out" ]; then echo '{"dependencies": [], "fixes": []}' > "$out"; fi
exit 0
"""


def _audit(
    tmp_path: Path, requirements: str, ignore: str = "", findings: str = ""
) -> tuple[int, str, list[list[str]]]:
    """Run the action's script. Returns the exit code, the output, and for
    every pip-audit call its arguments followed by the pins it got."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(FAKE_UV)
    uv.chmod(0o755)
    script = tmp_path / "audit.sh"
    script.write_text(STEP["run"])
    req = tmp_path / "versions.txt"
    req.write_text(requirements)
    log = tmp_path / "uv.log"
    log.touch()
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "UV_LOG": str(log),
        "REQUIREMENTS": str(req),
        "IGNORE_VULNS": ignore,
        "FINDINGS": findings,
        "PINNED_IN": "uv.lock",
        "GITHUB_ACTION_PATH": str(ACTION_DIR),
        "RUNNER_TEMP": str(tmp_path),
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
        assert "--strict --no-deps --disable-pip" in call[0]
        assert "--format json" not in call[0]
        assert call[1:] == ["idna==3.15", "requests==2.33.1"]


def test_pip_audit_comes_from_the_lockfile_of_the_action(tmp_path):
    """The version is in uv.lock next to the action, and its environment goes
    into the runner's temporary folder."""
    _, _, calls = _audit(tmp_path, "idna==3.15\n")
    for call in calls:
        assert call[0].startswith(
            f"run --quiet --frozen --project {ACTION_DIR} pip-audit "
        )
        assert call[0].endswith(f" ENV {tmp_path}/pip-audit-env")
    lock = (ACTION_DIR / "uv.lock").read_text("utf-8")
    assert '\nname = "pip-audit"\n' in lock


def test_the_project_of_the_action_is_no_package():
    project = (ACTION_DIR / "pyproject.toml").read_text("utf-8")
    assert '"pip-audit>=' in project and "package = false" in project


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
    _, _, calls = _audit(
        tmp_path, "idna==3.15\n", ignore="GHSA-aaaa-bbbb-cccc PYSEC-2026-1"
    )
    for call in calls:
        assert "--ignore-vuln GHSA-aaaa-bbbb-cccc --ignore-vuln PYSEC-2026-1" in call[0]


def test_a_finding_fails_the_audit_after_every_call(tmp_path):
    code, _, calls = _audit(tmp_path, "bad==1.0\n")
    assert code == 1 and len(calls) == 2


def test_with_findings_a_vulnerability_is_written_and_fails_nothing(tmp_path):
    """The audit job of freshness.yml reports instead of failing."""
    out = tmp_path / "findings"
    code, _, calls = _audit(tmp_path, "bad==1.0\nidna==3.15\n", findings=str(out))
    assert code == 0
    assert len(calls) == 2
    for call in calls:
        assert "--format json --output " in call[0]
    lines = (out / "findings.jsonl").read_text().splitlines()
    assert [json.loads(line)["vulnerability"] for line in lines] == [
        "GHSA-bad0-bad0-bad0"
    ]
    assert json.loads((out / "status.json").read_text()) == {
        "result": "ok",
        "checked": 1,
    }


def test_with_findings_a_package_that_cannot_be_audited_still_fails(tmp_path):
    out = tmp_path / "findings"
    code, _, _ = _audit(tmp_path, "broken==1.0\n", findings=str(out))
    assert code == 1
    assert not out.exists()


@pytest.mark.parametrize("requirements", ["", "# only a comment\n"])
def test_nothing_to_audit_is_an_error(tmp_path, requirements):
    code, out, calls = _audit(tmp_path, requirements)
    assert code == 1 and calls == []
    assert "::error::" in out


def test_the_action_installs_uv_itself():
    """Like every action here that needs uv, so no caller has to know."""
    assert UV_STEP["uses"].startswith("astral-sh/setup-uv@")
