"""The wiring of freshness.yml: which job runs on which switch, how the
ecosystem picks the adapter, and that every finding reaches the report and
the report the issue.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = yaml.safe_load(
    (ROOT / ".github" / "workflows" / "freshness.yml").read_text("utf-8")
)
INPUTS = WORKFLOW[True]["workflow_call"]["inputs"]
JOBS = WORKFLOW["jobs"]
MEASURING = ("outdated", "audit", "images", "actions")
IMAGES_ACTION = yaml.safe_load(
    (ROOT / "actions" / "freshness" / "images" / "action.yml").read_text("utf-8")
)
AUDIT_ACTION = yaml.safe_load(
    (ROOT / "actions" / "python" / "freshness-audit" / "action.yml").read_text("utf-8")
)
AUDIT_WORKFLOW = yaml.safe_load(
    (ROOT / ".github" / "workflows" / "python-dependency-audit.yml").read_text("utf-8")
)


def _step(job: str, uses_prefix: str) -> dict:
    (step,) = [
        s for s in JOBS[job]["steps"] if str(s.get("uses", "")).startswith(uses_prefix)
    ]
    return step


def test_the_issue_title_has_no_default_and_the_switches_are_on():
    assert INPUTS["issue-title"]["required"] is True
    assert "default" not in INPUTS["issue-title"]
    for job in MEASURING:
        assert INPUTS[job] == {
            "description": f"Run the {job} job.",
            "type": "boolean",
            "default": True,
        }
    assert INPUTS["ecosystem"]["default"] == "uv"
    assert INPUTS["dev"]["default"] is False
    assert (
        INPUTS["platforms"]["default"]
        == IMAGES_ACTION["inputs"]["platforms"]["default"]
    )


def test_the_workflow_itself_only_reads_and_the_report_writes_issues():
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert JOBS["report"]["permissions"] == {"contents": "read", "issues": "write"}
    for job in MEASURING:
        assert "permissions" not in JOBS[job]


@pytest.mark.parametrize("job", MEASURING)
def test_each_measuring_job_runs_on_its_switch_and_leaves_its_artifact(job):
    assert JOBS[job]["if"] == f"inputs.{job}"
    upload = _step(job, "actions/upload-artifact@")
    assert upload["with"]["name"] == f"freshness-{job}"
    assert upload["with"]["path"] == f"${{{{ runner.temp }}}}/freshness/{job}"
    checkout = _step(job, "actions/checkout@")
    assert checkout["with"]["persist-credentials"] is False
    assert JOBS[job]["timeout-minutes"] == "${{ inputs.timeout-minutes }}"


@pytest.mark.parametrize(
    ("job", "action"),
    [("outdated", "freshness-outdated"), ("audit", "freshness-audit")],
)
def test_the_ecosystem_picks_the_adapter_and_an_unknown_one_fails(job, action):
    adapter = _step(job, f"benethos-hub/.github/actions/python/{action}@main")
    assert adapter["if"] == "inputs.ecosystem == 'uv'"
    assert adapter["with"]["findings"] == f"${{{{ runner.temp }}}}/freshness/{job}"
    (guard,) = [
        s for s in JOBS[job]["steps"] if s.get("if") == "inputs.ecosystem != 'uv'"
    ]
    assert "exit 1" in guard["run"]
    assert guard["env"]["ECOSYSTEM"] == "${{ inputs.ecosystem }}"


def test_the_language_neutral_jobs_know_no_ecosystem():
    for job in ("images", "actions"):
        assert all("ecosystem" not in str(s.get("if", "")) for s in JOBS[job]["steps"])
    images = _step("images", "benethos-hub/.github/actions/freshness/images@main")
    assert images["with"]["platforms"] == "${{ inputs.platforms }}"
    assert images["with"]["files"] == "${{ inputs.image-files }}"
    actions = _step("actions", "benethos-hub/.github/actions/freshness/actions@main")
    assert actions["with"] == {
        "findings": "${{ runner.temp }}/freshness/actions",
        "files": "${{ inputs.action-files }}",
    }


def test_the_waivers_reach_the_audit():
    audit = _step("audit", "benethos-hub/.github/actions/python/freshness-audit@main")
    assert audit["with"]["ignore-vulns"] == "${{ inputs.ignore-vulns }}"


def test_the_report_runs_whatever_happened_and_knows_the_expected_jobs():
    report = JOBS["report"]
    assert report["needs"] == list(MEASURING)
    assert report["if"] == "always()"
    download = _step("report", "actions/download-artifact@")
    assert download["continue-on-error"] is True
    assert download["with"] == {
        "pattern": "freshness-*",
        "path": "${{ runner.temp }}/freshness",
    }
    (expected,) = [s for s in report["steps"] if s.get("id") == "expected"]
    for job in MEASURING:
        assert expected["env"][job.upper()] == f"${{{{ inputs.{job} }}}}"
        assert (
            f'[ "${job.upper()}" = true ] && expected="$expected {job}"'
            in expected["run"]
        )
    writer = _step("report", "benethos-hub/.github/actions/freshness/report@main")
    assert writer["with"] == {
        "results": "${{ runner.temp }}/freshness",
        "expected": "${{ steps.expected.outputs.jobs }}",
        "ignore": "${{ inputs.ignore }}",
        "dev": "${{ inputs.dev }}",
        "report": "${{ runner.temp }}/report.md",
    }
    issue = _step("report", "benethos-hub/.github/actions/report-issue@main")
    assert issue["with"] == {
        "title": "${{ inputs.issue-title }}",
        "report": "${{ runner.temp }}/report.md",
        "resolved": "${{ inputs.resolved }}",
    }


def test_the_audit_adapter_exports_like_the_dependency_audit_and_asks_for_findings():
    """The same export as python-dependency-audit.yml, so the same versions
    are audited: all members, all extras, all groups, every platform."""
    (export,) = [
        s
        for s in AUDIT_WORKFLOW["jobs"]["audit"]["steps"]
        if "uv export" in s.get("run", "")
    ]
    command = (
        export["run"].split("uv export", 1)[1].split(">")[0].replace("\\\n", "").split()
    )
    (adapter_export,) = [
        s for s in AUDIT_ACTION["runs"]["steps"] if "uv export" in s.get("run", "")
    ]
    adapter_command = (
        adapter_export["run"]
        .split("uv export", 1)[1]
        .split(">")[0]
        .replace("\\\n", "")
        .split()
    )
    assert adapter_command == command
    assert "Missing uv.lock" in adapter_export["run"]
    (audit,) = [
        s
        for s in AUDIT_ACTION["runs"]["steps"]
        if "pip-audit@" in str(s.get("uses", ""))
    ]
    assert audit["with"]["findings"] == "${{ inputs.findings }}"
    assert audit["with"]["pinned-in"] == "uv.lock"
    assert audit["with"]["ignore-vulns"] == "${{ inputs.ignore-vulns }}"
    assert audit["with"]["requirements"] == adapter_export["env"]["LOCKED"]
    assert set(AUDIT_ACTION["inputs"]) == {"findings", "ignore-vulns"}


def test_the_documentation_names_every_input_and_is_linked():
    page = (ROOT / "docs" / "freshness.md").read_text("utf-8")
    for name in INPUTS:
        assert f"`{name}`" in page, name
    for job in JOBS.values():
        assert f"`{job['name']}`" in page, job["name"]
    assert "(docs/freshness.md)" in (ROOT / "README.md").read_text("utf-8")
    assert "freshness.md" in (ROOT / "docs" / "new-repository.md").read_text("utf-8")
