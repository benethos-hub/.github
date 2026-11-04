"""The findings the pip-audit action writes for the freshness report: one per
vulnerability of a pinned version, merged across the two services.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "actions" / "python" / "pip-audit"
ACTION = yaml.safe_load((FOLDER / "action.yml").read_text("utf-8"))

_spec = importlib.util.spec_from_file_location(
    "pip_audit_findings", FOLDER / "findings.py"
)
assert _spec and _spec.loader
findings = importlib.util.module_from_spec(_spec)
sys.modules["pip_audit_findings"] = findings
_spec.loader.exec_module(findings)


def _report(*dependencies: dict[str, object]) -> dict[str, object]:
    return {"dependencies": list(dependencies), "fixes": []}


def _vuln(id: str, *aliases: str, fix: list[str] | None = None) -> dict[str, object]:
    return {
        "id": id,
        "aliases": list(aliases),
        "fix_versions": fix or [],
        "description": "x",
    }


PYPI = _report(
    {
        "name": "requests",
        "version": "2.25.0",
        "vulns": [_vuln("GHSA-9wx4-h78v-vm56", "CVE-2024-35195", fix=["2.32.0"])],
    },
    {"name": "idna", "version": "3.4", "vulns": []},
)
OSV = _report(
    {
        "name": "requests",
        "version": "2.25.0",
        "vulns": [
            _vuln(
                "PYSEC-2026-1873",
                "GHSA-9wx4-h78v-vm56",
                "CVE-2024-35195",
                fix=["2.32.0", "2.31.1"],
            )
        ],
    },
    {"name": "idna", "version": "3.4", "vulns": []},
)


def test_the_same_vulnerability_at_both_services_is_one_finding_named_by_its_ghsa_id():
    found, checked = findings.merge([PYPI, OSV], "uv.lock", set())
    assert checked == 2
    assert found == [
        {
            "category": "vulnerability",
            "name": "requests",
            "where": ["uv.lock"],
            "current": "2.25.0",
            "vulnerability": "GHSA-9wx4-h78v-vm56",
            "fix": ["2.31.1", "2.32.0"],
        }
    ]


def test_two_vulnerabilities_of_one_version_stay_apart():
    report = _report(
        {
            "name": "x",
            "version": "1.0",
            "vulns": [_vuln("PYSEC-1", fix=["1.1"]), _vuln("PYSEC-2")],
        }
    )
    found, _ = findings.merge([report], "uv.lock", set())
    assert [f["vulnerability"] for f in found] == ["PYSEC-1", "PYSEC-2"]
    assert found[1]["fix"] == []


def test_a_waiver_matches_any_id_of_the_vulnerability():
    found, checked = findings.merge([PYPI, OSV], "uv.lock", {"CVE-2024-35195"})
    assert found == []
    assert checked == 2


def test_a_version_pinned_twice_is_two_pinned_versions():
    report = _report(
        {"name": "numpy", "version": "2.4.6", "vulns": []},
        {"name": "numpy", "version": "2.5.4", "vulns": []},
    )
    assert findings.merge([report, report], "uv.lock", set()) == ([], 2)


def _run(tmp_path: Path, reports: list[dict[str, object]], **env: str):
    work = tmp_path / "work"
    work.mkdir()
    for number, report in enumerate(reports):
        (work / f"findings-pypi-part{number}.json").write_text(
            json.dumps(report), "utf-8"
        )
    return subprocess.run(
        [sys.executable, str(FOLDER / "findings.py")],
        env=os.environ
        | {"WORK": str(work), "FINDINGS": str(tmp_path / "out"), "PINNED_IN": "uv.lock"}
        | env,
        capture_output=True,
        text=True,
    )


def test_the_script_writes_the_findings_and_the_status(tmp_path):
    run = _run(tmp_path, [PYPI, OSV], IGNORE_VULNS="")
    assert run.returncode == 0, run.stderr
    lines = (tmp_path / "out" / "findings.jsonl").read_text("utf-8").splitlines()
    assert [json.loads(line)["name"] for line in lines] == ["requests"]
    status = json.loads((tmp_path / "out" / "status.json").read_text("utf-8"))
    assert status == {"result": "ok", "checked": 2}
    assert "2 pinned versions audited, 1 known vulnerabilities." in run.stdout


def test_no_output_of_pip_audit_is_an_error(tmp_path):
    run = _run(tmp_path, [])
    assert run.returncode == 1
    assert "nothing was audited" in run.stderr


# --- the action ---------------------------------------------------------------


def test_the_action_keeps_its_old_inputs_and_adds_the_findings():
    inputs = ACTION["inputs"]
    assert set(inputs) == {"requirements", "ignore-vulns", "findings", "pinned-in"}
    assert inputs["findings"]["default"] == ""
    assert inputs["pinned-in"]["default"] == "uv.lock"


def test_with_findings_a_vulnerability_is_a_finding_and_a_missing_file_a_failure():
    (step,) = [s for s in ACTION["runs"]["steps"] if "run" in s]
    run = step["run"]
    assert set(step["env"]) == {"REQUIREMENTS", "IGNORE_VULNS", "FINDINGS", "PINNED_IN"}
    assert 'if [ -n "$FINDINGS" ]; then' in run
    assert '--format json --output "$out" -r "$part" || true' in run
    assert '[ -s "$out" ] || failed=1' in run
    assert '"$GITHUB_ACTION_PATH/findings.py"' in run
    # Without findings, the call is the one of before.
    assert '-r "$part" || failed=1' in run
