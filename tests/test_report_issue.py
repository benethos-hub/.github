"""The action that keeps the issue of a scheduled report, run in bash with
a stand-in for the GitHub CLI.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION = yaml.safe_load(
    (ROOT / "actions" / "report-issue" / "action.yml").read_text("utf-8")
)

FAKE_GH = r"""#!/bin/bash
case "$*" in
  "issue list"*)
    printf '%s\n' "$*" >> "$GH_LIST_LOG"
    echo "$OPEN_ISSUE"
    ;;
  "issue view"*) printf '%s\n' "$OPEN_BODY" ;;
  issue*) printf 'gh %s\n' "$*" >> "$GH_LOG" ;;
  "api repos/"*"/releases/latest"*)
    [ -n "$LATEST_TAG" ] || { echo "HTTP 404" >&2; exit 1; }
    echo "$LATEST_TAG"
    ;;
  "api repos/"*"/compare/"*)
    printf '%s\n' "$*" >> "$GH_API_LOG"
    echo "$COMPARED"
    ;;
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
    title: str = TITLE,
    repository: str = "benethos-hub/.github",
    workflow: str = "Brand report",
    workflow_file: str = "brand-report.yml",
    open_body: str = "",
    run: dict[str, str] | None = None,
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
        "TITLE": title,
        "REPORT": str(tmp_path / "report.md"),
        "RESOLVED": "All repositories meet the brand rules.",
        "WORKFLOW": workflow,
        "WORKFLOW_REF": (
            f"{repository}/.github/workflows/{workflow_file}@refs/heads/main"
        ),
        "OPEN_ISSUE": open_issue,
        "OPEN_BODY": open_body,
        "GH_LOG": str(log),
        "GH_LIST_LOG": str(tmp_path / "gh-list.log"),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": repository,
        "GH_REPO": repository,
        "GH_API_LOG": str(tmp_path / "gh-api.log"),
        "LATEST_TAG": "",
        "COMPARED": "",
    } | (run or {})
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


def _closed_line() -> str:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return (
        f"**Closed on {day}.** All repositories meet the brand rules. "
        "The report below is the last one before that."
    )


def test_an_empty_report_marks_the_last_report_and_closes_the_issue(tmp_path):
    last = f"These repositories ...\n\n{FOOTER}"
    log, summary = _run(tmp_path, "", "2", open_body=last)
    assert log == (
        f"gh issue edit 2 --body {_closed_line()}\n\n{last}\n"
        "gh issue close 2 --comment All repositories meet the brand rules.\n"
    )
    assert summary == "All repositories meet the brand rules.\n"


def test_a_line_left_by_a_run_that_stopped_is_not_doubled(tmp_path):
    last = f"These repositories ...\n\n{FOOTER}"
    earlier = (
        "**Closed on 2026-11-06.** All repositories meet the brand rules. "
        "The report below is the last one before that."
    )
    log, _ = _run(tmp_path, "", "2", open_body=f"{earlier}\n\n{last}")
    assert log.startswith(f"gh issue edit 2 --body {_closed_line()}\n\n{last}\n")
    assert log.count("Closed on") == 1


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


def test_a_quote_in_the_title_stays_out_of_the_filter(tmp_path):
    title = 'Pins "really" need an update'
    log, _ = _run(tmp_path, "A report", "", title=title)
    listing = (tmp_path / "gh-list.log").read_text()
    assert "select(.title == env.TITLE)" in listing
    assert "really" not in listing
    assert log.startswith(f"gh issue create --title {title} --body ")


SHA = "3898e98a" + "0" * 32
BASE = "https://github.com/benethos-hub/example"
RUN = {"GITHUB_SHA": SHA, "GITHUB_REF_NAME": "main", "GITHUB_RUN_ID": "44045392649"}
WHEN = r" on \d{4}-\d\d-\d\d at \d\d:\d\d UTC\. "


def _checked(release: str) -> str:
    """The line as a pattern, the time left open."""
    return (
        re.escape(f"Checked on commit [`3898e98`]({BASE}/commit/{SHA}) of `main`")
        + re.escape(release)
        + re.escape(f", in [run 44045392649]({BASE}/actions/runs/44045392649)")
        + WHEN
    )


@pytest.mark.parametrize(
    ("tag", "compared", "release"),
    [
        (
            "v0.9.1",
            "ahead 2",
            f", 2 commits after [`v0.9.1`]({BASE}/releases/tag/v0.9.1)",
        ),
        (
            "v0.9.1",
            "ahead 1",
            f", 1 commit after [`v0.9.1`]({BASE}/releases/tag/v0.9.1)",
        ),
        ("v0.9.1", "identical 0", f", tagged [`v0.9.1`]({BASE}/releases/tag/v0.9.1)"),
        ("v0.9.1", "behind 0", ""),
        ("v0.9.1", "diverged 3", ""),
        ("", "", ""),
    ],
)
def test_the_body_says_which_commit_was_checked(tmp_path, tag, compared, release):
    run = RUN | {"LATEST_TAG": tag, "COMPARED": compared}
    log, _ = _run(
        tmp_path,
        "A report",
        "",
        repository="benethos-hub/example",
        workflow="Freshness",
        workflow_file="freshness.yml",
        run=run,
    )
    footer = re.escape("This issue is updated by the [Freshness]")
    assert re.search("\n\n" + _checked(release) + footer, log), log
    if tag:
        calls = (tmp_path / "gh-api.log").read_text()
        assert f"repos/benethos-hub/example/compare/{tag}...{SHA}" in calls


def test_the_closing_line_names_the_commit_and_the_run(tmp_path):
    last = f"These repositories ...\n\n{FOOTER}"
    run = RUN | {"LATEST_TAG": "v0.9.1", "COMPARED": "identical 0"}
    log, _ = _run(
        tmp_path, "", "2", repository="benethos-hub/example", open_body=last, run=run
    )
    closed = (
        re.escape(
            _closed_line().removesuffix(
                " The report below is the last one before that."
            )
            + " "
        )
        + _checked(f", tagged [`v0.9.1`]({BASE}/releases/tag/v0.9.1)")
        + re.escape("The report below is the last one before that.\n\n" + last)
    )
    assert re.match("gh issue edit 2 --body " + closed, log), log


def test_the_step_gets_its_inputs_and_the_calling_workflow():
    (step,) = ACTION["runs"]["steps"]
    assert step["env"]["GH_REPO"] == "${{ github.repository }}"
    assert step["env"]["WORKFLOW_REF"] == "${{ github.workflow_ref }}"
    assert step["env"]["GH_TOKEN"] == "${{ inputs.token }}"
    assert ACTION["inputs"]["token"]["default"] == "${{ github.token }}"
