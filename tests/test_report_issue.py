"""The action that keeps the issue of a scheduled report, run in bash with
a stand-in for the GitHub CLI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION = yaml.safe_load(
    (ROOT / "actions" / "report-issue" / "action.yml").read_text("utf-8")
)

FAKE_GH = r"""#!/bin/bash
case "$*" in
  "issue list"*) echo "$OPEN_ISSUE" ;;
  issue*) printf 'gh %s\n' "$*" >> "$GH_LOG" ;;
esac
"""

TITLE = "Brand assets need fixing"
FOOTER = (
    "This issue is updated by the [Brand report]"
    "(https://github.com/benethos-hub/.github/actions/workflows/brand-report.yml) "
    "workflow and closed once nothing is left to report."
)


def _run(
    tmp_path: Path,
    report: str,
    open_issue: str,
    *,
    repository: str = "benethos-hub/.github",
    workflow: str = "Brand report",
    workflow_file: str = "brand-report.yml",
) -> tuple[str, str]:
    (step,) = ACTION["runs"]["steps"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    (tmp_path / "report.md").write_text(report, "utf-8")
    log = tmp_path / "gh.log"
    log.touch()
    summary = tmp_path / "summary.md"
    script = tmp_path / "step.sh"
    script.write_text(step["run"])
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "TITLE": TITLE,
        "REPORT": str(tmp_path / "report.md"),
        "RESOLVED": "All repositories meet the brand rules.",
        "WORKFLOW": workflow,
        "WORKFLOW_REF": (
            f"{repository}/.github/workflows/{workflow_file}@refs/heads/main"
        ),
        "OPEN_ISSUE": open_issue,
        "GH_LOG": str(log),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": repository,
    }
    done = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    return log.read_text(), summary.read_text()


pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the step runs in bash")


@pytest.mark.parametrize(
    ("open_issue", "expected"),
    [
        ("", f"gh issue create --title {TITLE} --body "),
        ("2", "gh issue edit 2 --body "),
    ],
)
def test_a_report_becomes_the_body_with_a_link_to_the_workflow(
    tmp_path, open_issue, expected
):
    log, summary = _run(tmp_path, "These repositories ...", open_issue)
    body = f"These repositories ...\n\n{FOOTER}\n"
    assert log == expected + body
    assert summary == body


def test_an_empty_report_closes_the_open_issue(tmp_path):
    log, summary = _run(tmp_path, "", "2")
    assert log == (
        "gh issue close 2 --comment All repositories meet the brand rules.\n"
    )
    assert summary == "All repositories meet the brand rules.\n"


def test_an_empty_report_without_an_open_issue_does_nothing(tmp_path):
    assert _run(tmp_path, "", "")[0] == ""


def test_the_link_points_to_the_calling_repository(tmp_path):
    log, _ = _run(
        tmp_path,
        "A report",
        "",
        repository="benethos-hub/example",
        workflow="Daily check",
        workflow_file="daily-check.yml",
    )
    assert (
        "[Daily check](https://github.com/benethos-hub/example"
        "/actions/workflows/daily-check.yml)"
    ) in log


def test_the_step_gets_its_inputs_and_the_calling_workflow():
    (step,) = ACTION["runs"]["steps"]
    assert step["env"]["GH_REPO"] == "${{ github.repository }}"
    assert step["env"]["WORKFLOW_REF"] == "${{ github.workflow_ref }}"
    assert step["env"]["GH_TOKEN"] == "${{ inputs.token }}"
    assert ACTION["inputs"]["token"]["default"] == "${{ github.token }}"
