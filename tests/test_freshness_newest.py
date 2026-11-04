"""The ready-made job on the newest versions allowed: what moved against the
lockfile, when the run says something and when it does not, and what it
leaves for the alarm issue.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "actions" / "python" / "freshness-newest"
ACTION = yaml.safe_load((FOLDER / "action.yml").read_text("utf-8"))

_spec = importlib.util.spec_from_file_location("freshness_newest", FOLDER / "newest.py")
assert _spec and _spec.loader
newest = importlib.util.module_from_spec(_spec)
sys.modules["freshness_newest"] = newest
_spec.loader.exec_module(newest)


def _package(name: str, version: str, body: str = "") -> str:
    return f'[[package]]\nname = "{name}"\nversion = "{version}"\n{body}\n'


def _lock(**versions: str) -> str:
    """A project with mcp and two forks of soupsieve at runtime, pytest in
    the dev extra. Versions override the defaults."""
    v = {
        "mcp": "2.3.0",
        "anyio": "4.16.0",
        "soupsieve_a": "2.10",
        "soupsieve_b": "4.0",
        "pytest": "9.2.0",
    } | versions
    return "\n".join(
        [
            _package(
                "example",
                "1.0.0",
                'source = { editable = "." }\n'
                "dependencies = [\n"
                '    { name = "mcp" },\n'
                f'    {{ name = "soupsieve", version = "{v["soupsieve_a"]}" }},\n'
                f'    {{ name = "soupsieve", version = "{v["soupsieve_b"]}" }},\n'
                "]\n"
                '[package.optional-dependencies]\ndev = [{ name = "pytest" }]\n',
            ),
            _package("mcp", v["mcp"], 'dependencies = [{ name = "anyio" }]\n'),
            _package("anyio", v["anyio"]),
            _package("soupsieve", v["soupsieve_a"]),
            _package("soupsieve", v["soupsieve_b"]),
            _package("pytest", v["pytest"]),
        ]
    )


BEFORE = newest.outdated.load_lock(_lock())


def _after(**versions: str):
    return newest.outdated.load_lock(_lock(**versions))


# --- what moved -----------------------------------------------------------------


def test_only_runtime_packages_count_and_a_fork_is_one_line():
    after = _after(mcp="2.3.2", soupsieve_b="4.0.1", pytest="9.3.0")
    assert newest.moved(BEFORE, after) == [
        ("mcp", "2.3.0", "2.3.2"),
        ("soupsieve", "2.10, 4.0", "2.10, 4.0.1"),
    ]


def test_nothing_moved():
    assert newest.moved(BEFORE, _after()) == []
    assert newest.moved(BEFORE, _after(pytest="9.3.0")) == []


# --- the verdict ----------------------------------------------------------------


MOVED = [("mcp", "2.3.0", "2.3.2")]


@pytest.mark.parametrize(
    ("changes", "locked", "tests", "check", "expected"),
    [
        (MOVED, "success", "success", "success", "ok"),
        (MOVED, "skipped", "success", "skipped", "ok"),
        (MOVED, "success", "failure", "success", "ok"),
        (MOVED, "success", "success", "failure", "ok"),
        (MOVED, "failure", "failure", "failure", "inconclusive"),
        (MOVED, "rate-limited", "success", "success", "inconclusive"),
        (MOVED, "success", "success", "rate-limited", "inconclusive"),
        ([], "success", "failure", "success", "inconclusive"),
        ([], "success", "success", "success", "ok"),
    ],
)
def test_when_the_run_says_something(changes, locked, tests, check, expected):
    assert newest.verdict(changes, locked, tests, check) == expected


@pytest.mark.parametrize(
    ("locked", "tests", "check", "expected"),
    [
        (
            "failure",
            "failure",
            "failure",
            "the check failed on the locked versions as well",
        ),
        (
            "rate-limited",
            "success",
            "success",
            "the check hit a rate limit on the locked versions",
        ),
        (
            "success",
            "success",
            "rate-limited",
            "the check hit a rate limit on the newest versions allowed",
        ),
        (
            "success",
            "failure",
            "success",
            "the tests failed although nothing moved against uv.lock",
        ),
        (
            "success",
            "success",
            "failure",
            "the check failed although nothing moved against uv.lock",
        ),
    ],
)
def test_the_reason_of_an_inconclusive_run(locked, tests, check, expected):
    assert newest.reason([], locked, tests, check) == expected


# --- the summary and the section ------------------------------------------------


def test_the_summary_names_what_passed_and_what_moved():
    assert newest.summary(MOVED, "success") == (
        "the tests and the check passed on the newest versions allowed (mcp 2.3.2)"
    )
    assert newest.summary(MOVED, "skipped") == (
        "the tests passed on the newest versions allowed (mcp 2.3.2)"
    )
    assert newest.summary([], "skipped") == (
        "the tests passed, uv.lock already holds the newest versions allowed"
    )


def test_the_section_names_the_step_and_what_moved():
    changes = [("mcp", "2.3.0", "2.3.2"), ("soupsieve", "2.10, 4.0", "2.10, 4.0.1")]
    text = newest.section(changes, "failure", "success", "uv run pytest", "smoke")
    assert "- Tests: failure, `uv run pytest`" in text
    assert "- Check: success, `smoke`" in text
    assert "| `mcp` | 2.3.0 | 2.3.2 | patch |" in text
    assert "| `soupsieve` | 2.10, 4.0 | 2.10, 4.0.1 | patch |" in text
    assert newest.section(changes, "success", "success", "t", "c") == ""
    assert newest.section([], "failure", "failure", "t", "c") == ""


def test_the_section_leaves_a_skipped_check_out():
    text = newest.section(MOVED, "failure", "skipped", "uv run pytest", "")
    assert "- Check:" not in text


# --- the script -----------------------------------------------------------------


def _run(tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "before.lock").write_text(_lock(), "utf-8")
    (tmp_path / "after.lock").write_text(_lock(mcp="2.3.2"), "utf-8")
    return subprocess.run(
        [sys.executable, str(FOLDER / "newest.py")],
        env=os.environ
        | {
            "BEFORE": str(tmp_path / "before.lock"),
            "AFTER": str(tmp_path / "after.lock"),
            "LOCKED": "success",
            "TESTS": "success",
            "CHECK": "success",
            "TESTS_COMMAND": "uv run --frozen pytest -q",
            "CHECK_COMMAND": "smoke",
            "FINDINGS": str(tmp_path / "out"),
        }
        | env,
        capture_output=True,
        text=True,
    )


def test_a_passed_run_writes_the_summary_for_the_alarm(tmp_path):
    run = _run(tmp_path)
    assert run.returncode == 0, run.stderr
    status = json.loads((tmp_path / "out" / "status.json").read_text("utf-8"))
    assert status == {
        "result": "ok",
        "checked": 3,
        "issue": "alarm",
        "summary": (
            "the tests and the check passed on the newest versions allowed (mcp 2.3.2)"
        ),
    }
    assert not (tmp_path / "out" / "section.md").exists()
    assert "newest: ok, 1 runtime packages moved." in run.stdout


def test_a_failed_run_writes_the_section_and_no_summary(tmp_path):
    run = _run(tmp_path, TESTS="failure")
    assert run.returncode == 0, run.stderr
    status = json.loads((tmp_path / "out" / "status.json").read_text("utf-8"))
    assert status == {"result": "ok", "checked": 3, "issue": "alarm", "summary": ""}
    assert "- Tests: failure" in (tmp_path / "out" / "section.md").read_text("utf-8")


def test_an_inconclusive_run_writes_its_reason(tmp_path):
    run = _run(tmp_path, LOCKED="rate-limited")
    assert run.returncode == 0, run.stderr
    status = json.loads((tmp_path / "out" / "status.json").read_text("utf-8"))
    assert status["result"] == "inconclusive"
    assert status["summary"] == "the check hit a rate limit on the locked versions"
    assert not (tmp_path / "out" / "section.md").exists()


def test_a_missing_lockfile_fails_the_script(tmp_path):
    run = _run(tmp_path, BEFORE=str(tmp_path / "nowhere.lock"))
    assert run.returncode == 1
    assert "::error::Could not read the lockfiles" in run.stderr


# --- the action -----------------------------------------------------------------


def test_the_action_syncs_tests_and_checks_and_hands_the_outcomes_over():
    assert set(ACTION["inputs"]) == {
        "findings",
        "extras",
        "groups",
        "tests",
        "check",
        "rate-limit-exit-code",
    }
    assert ACTION["inputs"]["tests"]["default"] == "uv run --frozen pytest -q"
    assert ACTION["inputs"]["rate-limit-exit-code"]["default"] == "3"
    (run,) = [s for s in ACTION["runs"]["steps"] if "run" in s]
    script = run["run"]
    assert "sync=(uv sync --frozen)" in script
    assert 'cp uv.lock "$WORK/uv.lock.before"' in script
    assert "uv lock --upgrade\n" in script
    assert 'bash -c "$TESTS_COMMAND" || tests=failure' in script
    assert 'bash -c "$CHECK_COMMAND" >&2 || code=$?' in script
    assert 'export LOCKED="$locked" TESTS="$tests" CHECK="$newest"' in script
    assert '"$GITHUB_ACTION_PATH/newest.py"' in script
    assert set(run["env"]) == {
        "EXTRAS",
        "GROUPS",
        "TESTS_COMMAND",
        "CHECK_COMMAND",
        "RATE_LIMIT_EXIT",
        "FINDINGS",
        "WORK",
    }
