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
MEASURING = ("outdated", "audit", "images", "actions", "index")
MATRIX = {"outdated": "project", "audit": "project", "index": "package"}
ON_BY_DEFAULT = {
    "outdated": True,
    "audit": True,
    "images": True,
    "actions": True,
    "index": False,
}
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
        assert INPUTS[job]["type"] == "boolean"
        assert INPUTS[job]["default"] is ON_BY_DEFAULT[job]
        assert INPUTS[job]["description"].startswith(f"Run the {job} job")
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
    suffix = "${{ steps.artifact.outputs.suffix }}" if job in MATRIX else ""
    assert upload["with"]["name"] == f"freshness-{job}{suffix}"
    assert upload["with"]["path"] == f"${{{{ runner.temp }}}}/freshness/{job}"
    assert upload["with"]["retention-days"] == "${{ inputs.retention-days }}"
    checkout = _step(job, "actions/checkout@")
    assert checkout["with"]["persist-credentials"] is False
    assert JOBS[job]["timeout-minutes"] == "${{ inputs.timeout-minutes }}"


@pytest.mark.parametrize(
    ("job", "action"),
    [
        ("outdated", "freshness-outdated"),
        ("audit", "freshness-audit"),
        ("index", "freshness-index"),
    ],
)
def test_the_ecosystem_picks_the_adapter_and_an_unknown_one_fails(job, action):
    adapter = _step(job, f"benethos-hub/.github/actions/python/{action}@main")
    assert adapter["if"] == "inputs.ecosystem == 'uv'"
    assert adapter["with"]["findings"] == f"${{{{ runner.temp }}}}/freshness/{job}"
    if job != "index":
        assert adapter["with"]["directory"] == "${{ matrix.project }}"
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


@pytest.mark.parametrize("job", sorted(MATRIX))
def test_a_job_with_several_runs_names_its_artifact_per_run(job):
    key = MATRIX[job]
    source = "projects" if key == "project" else "index-packages"
    assert JOBS[job]["strategy"] == {
        "fail-fast": False,
        "matrix": {key: f"${{{{ fromJSON(inputs.{source}) }}}}"},
    }
    (named,) = [s for s in JOBS[job]["steps"] if s.get("id") == "artifact"]
    assert named["env"] == {key.upper(): f"${{{{ matrix.{key} }}}}"}
    assert "tr -c 'A-Za-z0-9\\n' '-'" in named["run"]
    assert 'echo "suffix=$suffix" >> "$GITHUB_OUTPUT"' in named["run"]


def test_the_default_lists_are_the_root_and_the_one_project():
    assert INPUTS["projects"]["default"] == '["."]'
    assert INPUTS["index-packages"]["default"] == '[""]'
    assert "index-package" not in INPUTS


def test_the_expected_jobs_carry_the_same_suffixes():
    (expected,) = [s for s in JOBS["report"]["steps"] if s.get("id") == "expected"]
    assert expected["env"]["PROJECTS"] == "${{ inputs.projects }}"
    assert expected["env"]["INDEX_PACKAGES"] == "${{ inputs.index-packages }}"
    run = expected["run"]
    assert "slug() { printf '%s' \"$1\" | tr -c 'A-Za-z0-9\\n' '-'; }" in run
    assert 'expected="$expected outdated$suffix"' in run
    assert 'expected="$expected audit$suffix"' in run
    assert 'expected="$expected index$suffix"' in run
    assert 'jq -r \'.[] | if . == "" then "." else . end\'' in run


def test_the_index_job_passes_the_package_the_check_and_the_python():
    adapter = _step("index", "benethos-hub/.github/actions/python/freshness-index@main")
    assert adapter["with"] == {
        "findings": "${{ runner.temp }}/freshness/index",
        "package": "${{ matrix.package }}",
        "check": "${{ inputs.index-check }}",
        "python": "${{ inputs.index-python }}",
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
    for job in ("images", "actions"):
        assert (
            f'[ "${job.upper()}" = true ] && expected="$expected {job}"'
            in expected["run"]
        )
    assert expected["env"]["EXTRA_JOBS"] == "${{ inputs.extra-jobs }}"
    assert 'expected="$expected $EXTRA_JOBS"' in expected["run"]
    writer = _step("report", "benethos-hub/.github/actions/freshness/report@main")
    assert writer["id"] == "report"
    assert writer["with"] == {
        "results": "${{ runner.temp }}/freshness",
        "expected": "${{ steps.expected.outputs.jobs }}",
        "ignore": "${{ inputs.ignore }}",
        "dev": "${{ inputs.dev }}",
        "report": "${{ runner.temp }}/report.md",
        "alarm": "${{ runner.temp }}/alarm.md",
    }
    issue, _alarm = _issue_steps()
    assert "if" not in issue
    assert issue["with"] == {
        "title": "${{ inputs.issue-title }}",
        "report": "${{ runner.temp }}/report.md",
        "resolved": "${{ inputs.resolved }}",
    }


def _issue_steps() -> list[dict]:
    return [
        s
        for s in JOBS["report"]["steps"]
        if str(s.get("uses", "")).startswith(
            "benethos-hub/.github/actions/report-issue@"
        )
    ]


def test_the_alarm_issue_is_kept_only_with_a_title_and_a_conclusive_run():
    _issue, alarm = _issue_steps()
    assert alarm["if"] == (
        "inputs.alarm-title != '' && steps.report.outputs.alarm == 'ready'"
    )
    assert alarm["with"] == {
        "title": "${{ inputs.alarm-title }}",
        "report": "${{ runner.temp }}/alarm.md",
        "resolved": "${{ inputs.alarm-resolved }}",
    }
    (note,) = [
        s for s in JOBS["report"]["steps"] if "left as it was" in s.get("run", "")
    ]
    assert note["if"] == (
        "inputs.alarm-title != '' && steps.report.outputs.alarm != 'ready'"
    )
    assert INPUTS["alarm-title"]["default"] == ""
    assert INPUTS["extra-jobs"]["default"] == ""
    assert "default" in INPUTS["alarm-resolved"]


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
        .replace('--directory "$DIRECTORY"', "")
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
    assert audit["with"]["pinned-in"] == "${{ steps.export.outputs.pinned }}"
    assert adapter_export["id"] == "export"
    assert 'pinned="${DIRECTORY#./}/uv.lock"' in adapter_export["run"]
    assert audit["with"]["ignore-vulns"] == "${{ inputs.ignore-vulns }}"
    assert audit["with"]["requirements"] == adapter_export["env"]["LOCKED"]
    assert set(AUDIT_ACTION["inputs"]) == {"findings", "ignore-vulns", "directory"}
    assert AUDIT_ACTION["inputs"]["directory"]["default"] == "."


def test_the_documentation_names_every_input_and_is_linked():
    page = (ROOT / "docs" / "freshness.md").read_text("utf-8")
    for name in INPUTS:
        assert f"`{name}`" in page, name
    for job in JOBS.values():
        assert f"`{job['name']}`" in page, job["name"]
    assert "(docs/freshness.md)" in (ROOT / "README.md").read_text("utf-8")
    assert "freshness.md" in (ROOT / "docs" / "new-repository.md").read_text("utf-8")
