"""The release gate: its script against canned API answers, and its wiring.

A mistake here shows only on a release, when a version is already on PyPI, so
the gate is held to what it promises. No test reaches the GitHub API.
"""

from __future__ import annotations

import importlib.util
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION_DIR = ROOT / "actions" / "release" / "ci-passed"
ACTION = yaml.safe_load((ACTION_DIR / "action.yml").read_text("utf-8"))
WORKFLOW = yaml.safe_load(
    (ROOT / ".github" / "workflows" / "python-release-ci-passed.yml").read_text("utf-8")
)

_spec = importlib.util.spec_from_file_location("ci_passed", ACTION_DIR / "ci_passed.py")
assert _spec and _spec.loader
ci_passed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci_passed)


def _run(status: str, conclusion: str | None = None, created: str = "1") -> dict:
    return {
        "status": status,
        "conclusion": conclusion,
        "created_at": f"2026-10-19T10:0{created}:00Z",
        "html_url": f"https://example.invalid/run/{created}",
    }


def _gate(
    answers: list[list[dict]], **kwargs: Any
) -> tuple[int, list[str], list[float]]:
    """Run the gate against canned API answers, the last one repeating."""
    urls: list[str] = []
    slept: list[float] = []

    def fetch(url: str) -> dict:
        urls.append(url)
        return {"workflow_runs": answers[min(len(urls), len(answers)) - 1]}

    code = ci_passed.check(
        "benethos-hub/example",
        "abc1234def",
        fetch=fetch,
        sleep=slept.append,
        **kwargs,
    )
    return code, urls, slept


# The script.


def test_a_green_run_on_main_lets_the_release_through():
    code, urls, slept = _gate([[_run("completed", "success")]])
    assert code == 0 and slept == []
    assert "head_sha=abc1234def" in urls[0]
    assert "event=push" in urls[0] and "branch=main" in urls[0]
    assert "/workflows/ci.yml/runs" in urls[0]


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_a_run_that_did_not_succeed_stops_the_release(conclusion, capsys):
    code, _, _ = _gate([[_run("completed", conclusion)]])
    assert code == 1
    assert capsys.readouterr().out.startswith("::error::CI on main ended")


def test_a_run_in_progress_is_waited_for():
    code, urls, slept = _gate(
        [[_run("queued")], [_run("in_progress")], [_run("completed", "success")]],
        interval=30,
    )
    assert code == 0 and len(urls) == 3 and slept == [30, 30]


def test_a_run_that_never_finishes_stops_the_release_after_the_wait(capsys):
    code, urls, _ = _gate([[_run("in_progress")]], wait_seconds=90, interval=30)
    assert code == 1 and len(urls) == 4
    assert "is still in_progress after 90 s" in capsys.readouterr().out


def test_a_commit_without_a_run_on_main_stops_soon(capsys):
    """A commit that never went into main gets no run, so the gate does not
    sit out the whole wait for one."""
    code, urls, _ = _gate([[]], wait_seconds=1800, interval=30, appear_seconds=60)
    assert code == 1 and len(urls) == 3
    assert "::error::No CI run on main" in capsys.readouterr().out


def test_the_newest_run_of_the_commit_decides():
    old_red = _run("completed", "failure", created="1")
    new_green = _run("completed", "success", created="2")
    older_green = new_green | {"created_at": "2026-10-19T09:00:00Z"}
    assert _gate([[old_red, new_green]])[0] == 0
    assert _gate([[older_green, old_red]])[0] == 1


def test_another_workflow_and_branch_reach_the_query(capsys):
    code, urls, _ = _gate(
        [[_run("completed", "success")]], workflow="tests.yml", branch="release/1.x"
    )
    assert code == 0
    assert "/workflows/tests.yml/runs" in urls[0]
    assert "branch=release%2F1.x" in urls[0]
    assert "CI passed on release/1.x" in capsys.readouterr().out


def test_main_reads_its_settings_from_the_environment(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_check(repository: str, sha: str, workflow: str, branch: str, **kwargs: Any) -> int:
        seen.update(repository=repository, sha=sha, workflow=workflow, branch=branch, **kwargs)
        return 0

    monkeypatch.setattr(ci_passed, "check", fake_check)
    monkeypatch.setenv("GITHUB_REPOSITORY", "benethos-hub/example")
    monkeypatch.setenv("GITHUB_SHA", "abc1234def")
    monkeypatch.setenv("CI_WORKFLOW", "")
    monkeypatch.setenv("CI_BRANCH", "trunk")
    monkeypatch.setenv("CI_WAIT_MINUTES", "2")
    monkeypatch.setenv("GITHUB_API_URL", "https://github.example.invalid/api/v3")
    assert ci_passed.main() == 0
    assert seen["workflow"] == "ci.yml"
    assert seen["branch"] == "trunk"
    assert seen["wait_seconds"] == 120
    assert seen["api"] == "https://github.example.invalid/api/v3"


def test_without_a_branch_the_release_stops(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_REPOSITORY", "benethos-hub/example")
    monkeypatch.setenv("GITHUB_SHA", "abc1234def")
    monkeypatch.setenv("CI_BRANCH", "")
    assert ci_passed.main() == 1
    assert "::error::No branch" in capsys.readouterr().out


def test_an_api_error_stops_the_release_with_a_hint(monkeypatch, capsys):
    def refused(*args: Any, **kwargs: Any) -> int:
        raise urllib.error.HTTPError("https://example.invalid", 403, "Forbidden", Message(), None)

    monkeypatch.setattr(ci_passed, "check", refused)
    monkeypatch.setenv("GITHUB_REPOSITORY", "benethos-hub/example")
    monkeypatch.setenv("GITHUB_SHA", "abc1234def")
    monkeypatch.setenv("CI_BRANCH", "main")
    assert ci_passed.main() == 1
    out = capsys.readouterr().out
    assert "::error::GitHub answered 403" in out and "actions: read" in out


# The wiring.


def test_the_action_runs_the_script_from_its_own_folder():
    """The repository that releases has no copy of the script."""
    uv, step = ACTION["runs"]["steps"]
    assert uv["uses"].startswith("astral-sh/setup-uv@")
    assert step["run"] == 'uv run --no-project "$GITHUB_ACTION_PATH/ci_passed.py"'
    assert step["env"]["CI_BRANCH"] == (
        "${{ inputs.branch || github.event.repository.default_branch }}"
    )
    assert step["env"]["GITHUB_TOKEN"] == "${{ inputs.token }}"


def test_the_action_and_the_workflow_share_their_defaults():
    action = ACTION["inputs"]
    workflow = WORKFLOW[True]["workflow_call"]["inputs"]
    assert action["workflow"]["default"] == workflow["workflow"]["default"] == "ci.yml"
    assert action["branch"]["default"] == workflow["branch"]["default"] == ""
    assert int(action["wait-minutes"]["default"]) == workflow["wait-minutes"]["default"] == 30
    assert workflow["timeout-minutes"]["default"] > workflow["wait-minutes"]["default"]


def test_the_gate_may_read_the_runs_and_passes_every_input():
    assert WORKFLOW["permissions"] == {"actions": "read", "contents": "read"}
    (step,) = WORKFLOW["jobs"]["ci-passed"]["steps"]
    assert step["uses"] == "benethos-hub/.github/actions/release/ci-passed@main"
    assert step["with"] == {
        "workflow": "${{ inputs.workflow }}",
        "branch": "${{ inputs.branch }}",
        "wait-minutes": "${{ inputs.wait-minutes }}",
    }


def test_the_audit_runs_only_when_asked_for():
    audit = WORKFLOW["jobs"]["audit"]
    assert audit["if"] == "inputs.audit"
    assert audit["uses"] == (
        "benethos-hub/.github/.github/workflows/python-dependency-audit.yml@main"
    )
    assert audit["with"] == {"ignore-vulns": "${{ inputs.ignore-vulns }}"}
    assert WORKFLOW[True]["workflow_call"]["inputs"]["audit"]["default"] is False
