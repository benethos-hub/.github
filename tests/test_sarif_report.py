"""The SARIF report: the script against files the three scanners wrote, and
the wiring of the action that runs it after every scanner.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml
from scanner_wiring import assert_reports_only_by_default

ROOT = Path(__file__).resolve().parent.parent
ACTION_DIR = ROOT / "actions" / "sarif-report"
ACTION = yaml.safe_load((ACTION_DIR / "action.yml").read_text("utf-8"))
FIXTURES = ROOT / "tests" / "fixtures" / "sarif"

_spec = importlib.util.spec_from_file_location(
    "sarif_report", ACTION_DIR / "sarif_report.py"
)
assert _spec and _spec.loader
sarif_report = importlib.util.module_from_spec(_spec)
# A dataclass looks its module up in sys.modules while it is being defined.
sys.modules["sarif_report"] = sarif_report
_spec.loader.exec_module(sarif_report)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.sarif").read_text("utf-8"))


@pytest.mark.parametrize(
    ("name", "tool", "errors", "warnings", "notes"),
    [
        ("hadolint", "Hadolint", 0, 4, 2),
        ("trivy", "Trivy", 3, 1, 1),
        ("checkov", "Checkov", 4, 0, 0),
        ("clean", "Checkov", 0, 0, 0),
    ],
)
def test_the_findings_of_each_scanner_are_counted_by_level(
    name, tool, errors, warnings, notes
):
    named, found = sarif_report.findings(_fixture(name))
    assert named == tool
    assert sarif_report.counts(found) == {
        "error": errors,
        "warning": warnings,
        "note": notes,
    }
    assert len(found) == errors + warnings + notes


def test_every_finding_names_rule_place_and_first_line_of_the_message():
    _, found = sarif_report.findings(_fixture("hadolint"))
    first = found[0]
    assert first.rule.startswith("DL")
    assert first.where.endswith("Dockerfile:1")
    assert "\n" not in first.message and first.message
    _, trivy = sarif_report.findings(_fixture("trivy"))
    assert all("\n" not in f.message for f in trivy)


def test_a_result_without_a_level_takes_the_rule_default_then_warning():
    sarif = {
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "T",
                        "rules": [
                            {"id": "R1", "defaultConfiguration": {"level": "error"}}
                        ],
                    }
                },
                "results": [
                    {"ruleId": "R1", "message": {"text": "a"}},
                    {"ruleId": "R2", "message": {"text": "b"}},
                    {"ruleId": "R3", "level": "none", "message": {"text": "c"}},
                ],
            }
        ]
    }
    _, found = sarif_report.findings(sarif)
    assert [f.level for f in found] == ["error", "warning"]
    assert found[0].where == ""


@pytest.mark.parametrize(
    ("name", "highest", "fails_at"),
    [
        (
            "hadolint",
            "warning",
            {"none": False, "note": True, "warning": True, "error": False},
        ),
        (
            "trivy",
            "error",
            {"none": False, "note": True, "warning": True, "error": True},
        ),
        ("checkov", "error", {"none": False, "error": True}),
        ("clean", "none", {"none": False, "note": False, "error": False}),
    ],
)
def test_the_highest_level_and_the_verdict_per_failure_level(name, highest, fails_at):
    _, found = sarif_report.findings(_fixture(name))
    assert sarif_report.highest(found) == highest
    for level, expected in fails_at.items():
        assert sarif_report.fails(found, level) is expected, level


def test_the_summary_is_a_table_sorted_by_level_and_cut_at_rows():
    _, found = sarif_report.findings(_fixture("trivy"))
    text = sarif_report.summary("Trivy", found, rows=2)
    lines = text.splitlines()
    assert lines[0] == "### Trivy: 5 findings"
    assert lines[2] == "3 error, 1 warning, 1 note"
    assert lines[4] == "| Level | Rule | Where | Message |"
    rows = [line for line in lines if line.startswith("| error")]
    assert len(rows) == 2
    assert "3 more in the SARIF file." in text
    assert "| warning" not in text


def test_a_clean_file_says_so_and_one_finding_is_singular():
    assert "Nothing to report." in sarif_report.summary("Checkov", [], 50)
    one = [sarif_report.Finding("note", "R", "f:1", "m | n")]
    text = sarif_report.summary("T", one, 50)
    assert text.startswith("### T: 1 finding\n")
    assert "| note | R | `f:1` | m \\| n |" in text


def _run_main(
    monkeypatch, tmp_path: Path, sarif: str, **env: str
) -> tuple[int, str, dict]:
    summary = tmp_path / "summary.md"
    output = tmp_path / "output.txt"
    monkeypatch.setenv("SARIF", sarif)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    for key in ("TOOL", "FAILURE_LEVEL", "ROWS"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    code = sarif_report.main()
    outputs = {}
    if output.exists():
        outputs = dict(
            line.split("=", 1) for line in output.read_text("utf-8").splitlines()
        )
    return code, summary.read_text("utf-8") if summary.exists() else "", outputs


def test_main_writes_summary_and_outputs_and_leaves_the_verdict_to_the_action(
    monkeypatch, tmp_path
):
    code, summary, outputs = _run_main(
        monkeypatch, tmp_path, str(FIXTURES / "hadolint.sarif"), FAILURE_LEVEL="warning"
    )
    assert code == 0
    assert summary.startswith("### Hadolint: 6 findings")
    assert outputs == {
        "findings": "6",
        "notes": "2",
        "warnings": "4",
        "errors": "0",
        "highest": "warning",
        "fail": "true",
    }


def test_main_takes_the_tool_name_given_and_none_never_fails(monkeypatch, tmp_path):
    code, summary, outputs = _run_main(
        monkeypatch, tmp_path, str(FIXTURES / "trivy.sarif"), TOOL="Trivy config"
    )
    assert code == 0
    assert summary.startswith("### Trivy config: 5 findings")
    assert outputs["fail"] == "false"


def test_main_fails_on_a_missing_file_a_broken_file_or_an_unknown_level(
    monkeypatch, tmp_path, capsys
):
    assert _run_main(monkeypatch, tmp_path, str(tmp_path / "none.sarif"))[0] == 1
    assert "is not a file" in capsys.readouterr().out
    broken = tmp_path / "broken.sarif"
    broken.write_text("{", "utf-8")
    assert _run_main(monkeypatch, tmp_path, str(broken))[0] == 1
    assert "is not JSON" in capsys.readouterr().out
    code, _, _ = _run_main(
        monkeypatch, tmp_path, str(FIXTURES / "clean.sarif"), FAILURE_LEVEL="high"
    )
    assert code == 1
    assert "failure-level is high" in capsys.readouterr().out


def test_the_action_reads_keeps_uploads_and_only_then_fails():
    inputs = ACTION["inputs"]
    assert inputs["sarif"]["required"] is True
    assert inputs["category"]["required"] is True
    assert_reports_only_by_default(ACTION)
    assert inputs["upload"]["default"] == "true"
    assert inputs["retention-days"]["default"] == "7"
    for name, spec in inputs.items():
        assert spec["description"], name
    names = [s["name"] for s in ACTION["runs"]["steps"]]
    assert names == [
        "Install uv",
        "Read the SARIF",
        "Keep the SARIF as an artifact",
        "Upload to code scanning",
        "Fail at the chosen level",
    ]
    uv, read, keep, upload, fail = ACTION["runs"]["steps"]
    assert uv["with"] == {"enable-cache": False}
    assert read["id"] == "report"
    assert read["env"] == {
        "SARIF": "${{ inputs.sarif }}",
        "TOOL": "${{ inputs.tool }}",
        "FAILURE_LEVEL": "${{ inputs.failure-level }}",
    }
    assert (
        'uv run --no-project --python ">=3.11" "$GITHUB_ACTION_PATH/sarif_report.py"'
        in read["run"]
    )
    assert keep["if"] == "inputs.artifact != ''"
    assert keep["uses"].startswith("actions/upload-artifact@")
    assert keep["with"]["retention-days"] == "${{ inputs.retention-days }}"
    assert upload["uses"].startswith("github/codeql-action/upload-sarif@")
    assert upload["if"] == (
        "inputs.upload == 'true' && !(github.event_name == 'pull_request' "
        "&& github.event.pull_request.head.repo.fork)"
    )
    assert upload["with"] == {
        "sarif_file": "${{ inputs.sarif }}",
        "category": "${{ inputs.category }}",
        "token": "${{ inputs.token }}",
    }
    assert fail["if"] == "steps.report.outputs.fail == 'true'"
    assert "exit 1" in fail["run"]
    for name in ("findings", "errors", "warnings", "notes", "highest"):
        assert (
            ACTION["outputs"][name]["value"]
            == f"${{{{ steps.report.outputs.{name} }}}}"
        )


def test_the_upload_and_the_codeql_action_share_one_pin():
    codeql = (ROOT / "actions" / "codeql" / "action.yml").read_text("utf-8")
    (pin,) = {
        line.split("@")[1].split()[0]
        for line in codeql.splitlines()
        if "github/codeql-action/" in line and "uses:" in line
    }
    upload = [
        s
        for s in ACTION["runs"]["steps"]
        if s.get("uses", "").startswith("github/codeql-action/")
    ]
    assert [s["uses"].split("@")[1] for s in upload] == [pin]
