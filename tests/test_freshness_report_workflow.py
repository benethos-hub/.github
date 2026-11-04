"""The wiring of freshness-report.yml: the report as a workflow of its own,
called by freshness.yml at the end of a run or by a repository after its
own jobs and the measuring call, and what the two share.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
REPORT = yaml.safe_load((WORKFLOWS / "freshness-report.yml").read_text("utf-8"))
MEASURE = yaml.safe_load((WORKFLOWS / "freshness.yml").read_text("utf-8"))
INPUTS = REPORT[True]["workflow_call"]["inputs"]
JOB = REPORT["jobs"]["report"]
SHARED = (
    "issue-title",
    "resolved",
    "extra-jobs",
    "alarm-title",
    "alarm-resolved",
    "ignore",
    "dev",
)


def _step(uses_prefix: str) -> dict:
    (step,) = [
        s for s in JOB["steps"] if str(s.get("uses", "")).startswith(uses_prefix)
    ]
    return step


def test_the_title_and_the_expected_jobs_are_required_and_the_rest_shared():
    assert INPUTS["issue-title"]["required"] is True
    assert INPUTS["expected"]["required"] is True
    assert "default" not in INPUTS["issue-title"]
    assert "default" not in INPUTS["expected"]
    assert set(INPUTS) == {*SHARED, "expected"}
    measure_inputs = MEASURE[True]["workflow_call"]["inputs"]
    for name in SHARED:
        assert INPUTS[name]["type"] == measure_inputs[name]["type"], name
        if name != "issue-title":
            assert INPUTS[name] == measure_inputs[name], name
    # The title is required here. The measuring workflow checks it itself,
    # since a call that only measures has no report to name.
    assert measure_inputs["issue-title"]["default"] == ""
    assert INPUTS["issue-title"]["description"].startswith(
        measure_inputs["issue-title"]["description"].split(" Required")[0]
    )


def test_the_report_is_the_only_job_and_writes_issues():
    assert list(REPORT["jobs"]) == ["report"]
    assert REPORT["permissions"] == {"contents": "read"}
    assert JOB["permissions"] == {"contents": "read", "issues": "write"}
    assert JOB["name"] == "Freshness report"
    assert JOB["timeout-minutes"] == 10


def test_an_empty_expected_list_stops_the_report_before_it_writes():
    first = JOB["steps"][0]
    assert first["env"] == {"EXPECTED": "${{ inputs.expected }}"}
    assert 'if [ -z "$(echo $EXPECTED)" ]' in first["run"]
    assert "exit 1" in first["run"]
    assert "if" not in first


def test_the_report_collects_every_artifact_and_knows_the_expected_jobs():
    download = _step("actions/download-artifact@")
    assert download["continue-on-error"] is True
    assert download["with"] == {
        "pattern": "freshness-*",
        "path": "${{ runner.temp }}/freshness",
    }
    writer = _step("benethos-hub/.github/actions/freshness/report@main")
    assert writer["id"] == "report"
    assert writer["with"] == {
        "results": "${{ runner.temp }}/freshness",
        "expected": "${{ inputs.expected }} ${{ inputs.extra-jobs }}",
        "ignore": "${{ inputs.ignore }}",
        "dev": "${{ inputs.dev }}",
        "report": "${{ runner.temp }}/report.md",
        "alarm": "${{ runner.temp }}/alarm.md",
    }


def _issue_steps() -> list[dict]:
    return [
        s
        for s in JOB["steps"]
        if str(s.get("uses", "")).startswith(
            "benethos-hub/.github/actions/report-issue@"
        )
    ]


def test_the_issue_is_kept_and_the_alarm_issue_only_when_conclusive():
    issue, alarm = _issue_steps()
    assert "if" not in issue
    assert issue["with"] == {
        "title": "${{ inputs.issue-title }}",
        "report": "${{ runner.temp }}/report.md",
        "resolved": "${{ inputs.resolved }}",
    }
    assert alarm["if"] == (
        "inputs.alarm-title != '' && steps.report.outputs.alarm == 'ready'"
    )
    assert alarm["with"] == {
        "title": "${{ inputs.alarm-title }}",
        "report": "${{ runner.temp }}/alarm.md",
        "resolved": "${{ inputs.alarm-resolved }}",
    }
    (note,) = [s for s in JOB["steps"] if "left as it was" in s.get("run", "")]
    assert note["if"] == (
        "inputs.alarm-title != '' && steps.report.outputs.alarm != 'ready'"
    )


def test_the_measuring_workflow_calls_it_with_its_own_expected_list():
    """The one-call form: freshness.yml hands its inputs and the output of
    its expected job to this workflow, and only when that job succeeded."""
    report = MEASURE["jobs"]["report"]
    assert report["uses"] == (
        "benethos-hub/.github/.github/workflows/freshness-report.yml@main"
    )
    assert report["with"] == {
        **{name: f"${{{{ inputs.{name} }}}}" for name in SHARED},
        "expected": "${{ needs.expected.outputs.jobs }}",
    }
    assert MEASURE[True]["workflow_call"]["outputs"]["expected"]["value"] == (
        "${{ jobs.expected.outputs.jobs }}"
    )


def test_the_two_workflows_pin_the_same_actions():
    """A bump of download-artifact lands in both, or the two drift apart."""
    download = _step("actions/download-artifact@")["uses"]
    header = (WORKFLOWS / "freshness-report.yml").read_text("utf-8")
    assert "freshness.yml with report off" in header
    assert download.startswith("actions/download-artifact@")
    assert download.count("@") == 1
