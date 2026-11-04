"""The report of the freshness workflow: what it names, what it only counts,
and that a job without a result never leaves it empty.
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
FOLDER = ROOT / "actions" / "freshness" / "report"
ACTION = yaml.safe_load((FOLDER / "action.yml").read_text("utf-8"))
FORMAT = (FOLDER / "FORMAT.md").read_text("utf-8")

_spec = importlib.util.spec_from_file_location("freshness_report", FOLDER / "report.py")
assert _spec and _spec.loader
report = importlib.util.module_from_spec(_spec)
sys.modules["freshness_report"] = report
_spec.loader.exec_module(report)


def _finding(**fields: object) -> dict[str, object]:
    return {
        "category": "package",
        "name": "mcp",
        "where": ["uv.lock"],
        "current": "2.3.0",
        "newest": "2.4.0",
    } | fields


def _job(
    results: Path,
    job: str,
    findings: list[dict[str, object]] | None = None,
    status: dict[str, object] | None = None,
    section: str = "",
) -> None:
    folder = results / f"freshness-{job}"
    folder.mkdir(parents=True)
    if status is not None:
        folder.joinpath("status.json").write_text(json.dumps(status), "utf-8")
    if findings is not None:
        lines = "".join(json.dumps(f) + "\n" for f in findings)
        folder.joinpath("findings.jsonl").write_text(lines, "utf-8")
    if section:
        folder.joinpath("section.md").write_text(section, "utf-8")


def _ok(
    results: Path, job: str, *findings: dict[str, object], **status: object
) -> None:
    _job(results, job, list(findings), {"result": "ok", "checked": 1} | status)


def _render(
    results: Path,
    expected: str = "",
    ignore: str = "",
    dev: bool = False,
    issue: str = "report",
):
    loaded = report.load_results(results, expected.split())
    return report.render(loaded, ignore.split(), dev, "", issue)


# --- kind -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "newest", "expected"),
    [
        ("2.3.0", "3.0.0", "major"),
        ("2.3.0", "2.4.0", "minor"),
        ("2.3.0", "2.3.1", "patch"),
        ("2.9.0.post0", "2.9.0.post1", "patch"),
        ("6.1", "6.1.3", "patch"),
        ("v7.0.1", "v7.1.0", "minor"),
        ("3.15-slim", "3.16-slim", "minor"),
        ("0.13.7", "0.14.0", "minor"),
        ("2026.4.26", "2026.5.4", "unknown"),
        ("0.7.0.20260504", "0.7.0.20260601", "unknown"),
        ("1.1.2.20261101", "1.1.3", "unknown"),
        ("sha256:8c13", "sha256:9d2e", "unknown"),
        ("main", "v2", "unknown"),
        ("1.0.0", "1.0.0", "unknown"),
    ],
)
def test_how_far_a_version_moved(current, newest, expected):
    assert report.kind(current, newest) == expected


# --- what is named and what is counted ---------------------------------------


def test_a_direct_runtime_package_is_named(tmp_path):
    _ok(tmp_path, "outdated", _finding(direct=True, within_bounds=False))
    text = _render(tmp_path, "outdated")
    assert "### Packages" in text
    assert "| `mcp` | 2.3.0 | 2.4.0 | minor | yes | no |" in text


def test_a_transitive_minor_alone_only_counts_and_leaves_the_report_empty(tmp_path):
    _ok(
        tmp_path,
        "outdated",
        _finding(name="h11", direct=False),
        _finding(name="certifi", current="2026.4.26", newest="2026.5.4", direct=False),
    )
    assert _render(tmp_path, "outdated") == ""


def test_a_transitive_major_is_named_and_the_rest_counted(tmp_path):
    _ok(
        tmp_path,
        "outdated",
        _finding(name="numpy", current="2.4.6", newest="3.0.0", direct=False),
        _finding(name="h11", direct=False),
    )
    text = _render(tmp_path, "outdated")
    assert "| `numpy` | 2.4.6 | 3.0.0 | major | no |" in text
    assert "1 more transitive, each a minor, a patch or an unknown kind." in text


def test_development_packages_are_hidden_and_do_not_open_the_issue(tmp_path):
    _ok(tmp_path, "outdated", _finding(name="pytest", scope="dev", direct=True))
    assert _render(tmp_path, "outdated") == ""


def test_development_packages_show_on_request(tmp_path):
    _ok(tmp_path, "outdated", _finding(name="pytest", scope="dev", direct=True))
    text = _render(tmp_path, "outdated", dev=True)
    assert "### Development packages" in text
    assert "| `pytest` |" in text


def test_the_hidden_development_packages_are_counted_beside_a_finding(tmp_path):
    _ok(
        tmp_path,
        "outdated",
        _finding(),
        _finding(name="pytest", scope="dev"),
        _finding(name="ruff", scope="dev"),
    )
    assert "2 development packages are not shown." in _render(tmp_path, "outdated")


def test_a_build_backend_is_named_with_every_file_that_pins_it(tmp_path):
    _ok(
        tmp_path,
        "outdated",
        _finding(
            name="hatchling",
            where=["pyproject.toml", "packages/a/pyproject.toml"],
            current="1.33.0",
            newest="1.34.0",
            scope="build",
        ),
    )
    text = _render(tmp_path, "outdated")
    assert "### Build backends" in text
    assert "| `hatchling` | 1.33.0 | 1.34.0 | minor | `pyproject.toml`, " in text
    assert "`packages/a/pyproject.toml` |" in text


def test_images_and_actions_are_always_named(tmp_path):
    _ok(
        tmp_path,
        "images",
        _finding(
            category="image",
            name="python:3.15-slim",
            where=["a/Dockerfile", "b/Dockerfile"],
            current="sha256:8c13",
            newest="sha256:9d2e",
            kind="rebuild",
        ),
    )
    _ok(
        tmp_path,
        "actions",
        _finding(
            category="action",
            name="actions/checkout",
            where=[".github/workflows/ci.yml"],
            current="v7.0.1",
            newest="v7.0.2",
        ),
    )
    text = _render(tmp_path, "images actions")
    assert "### Images" in text
    assert "| `python:3.15-slim` | sha256:8c13 | sha256:9d2e | rebuild |" in text
    assert "### Actions" in text
    assert "| `actions/checkout` | v7.0.1 | v7.0.2 | patch |" in text


def test_a_vulnerability_is_named_with_its_fix(tmp_path):
    _ok(
        tmp_path,
        "audit",
        _finding(
            category="vulnerability",
            name="example",
            current="1.0.0",
            newest="",
            vulnerability="GHSA-xxxx-xxxx-xxxx",
            fix=["1.0.1", "2.0.0"],
            direct=False,
        ),
    )
    text = _render(tmp_path, "audit")
    assert "### Known vulnerabilities" in text
    assert "| `example` | 1.0.0 | GHSA-xxxx-xxxx-xxxx | 1.0.1, 2.0.0 |  |" in text


def test_the_packages_column_appears_only_for_more_than_one_package(tmp_path):
    _ok(tmp_path, "outdated", _finding(packages=["a"]), packages=["a"])
    text = _render(tmp_path, "outdated")
    assert "Needed by" not in text

    _ok(
        tmp_path / "workspace",
        "outdated",
        _finding(packages=["a", "b"]),
        packages=["a", "b", "c"],
    )
    text = _render(tmp_path / "workspace", "outdated")
    assert "| Needed by |" in text
    assert "| `a`, `b` |" in text


# --- ignore -------------------------------------------------------------------


def test_ignored_findings_are_dropped_and_counted(tmp_path):
    _ok(
        tmp_path,
        "images",
        _finding(category="image", name="example/server", current="v0.16"),
        _finding(category="image", name="python", current="3.15-slim"),
    )
    text = _render(tmp_path, "images", ignore="example/*")
    assert "example/server" not in text
    assert "1 findings match the ignore patterns of the caller." in text


def test_only_ignored_findings_leave_the_report_empty(tmp_path):
    _ok(tmp_path, "images", _finding(category="image", name="example/server"))
    assert _render(tmp_path, "images", ignore="example/server") == ""


# --- a job without a result ---------------------------------------------------


def test_an_expected_job_without_an_artifact_is_reported(tmp_path):
    _ok(tmp_path, "outdated")
    text = _render(tmp_path, "outdated images")
    assert text != ""
    assert "The job `images` left no result" in text


def test_a_failed_job_is_reported(tmp_path):
    _job(tmp_path, "images", [], {"result": "failed", "checked": 0})
    assert "The job `images` failed" in _render(tmp_path, "images")


def test_a_job_without_its_status_counts_as_failed(tmp_path):
    (tmp_path / "freshness-images").mkdir()
    assert "The job `images` failed" in _render(tmp_path, "images")


def test_a_job_with_a_status_alone_is_a_result_without_findings(tmp_path):
    _job(tmp_path, "newest", None, {"result": "ok", "checked": 1})
    assert _render(tmp_path, "newest") == ""


# --- a section of prose and a second issue ------------------------------------------


def test_a_section_is_taken_over_after_the_tables_under_the_name_of_the_job(tmp_path):
    _ok(tmp_path, "images", _finding(category="image", name="python"))
    _job(
        tmp_path,
        "newest",
        None,
        {"result": "ok", "checked": 1},
        "The tests failed on `mcp` 2.4.0.\n\n- Tests: failure\n",
    )
    text = _render(tmp_path, "images newest")
    assert text.index("### Images") < text.index("### newest")
    section = "### newest\n\nThe tests failed on `mcp` 2.4.0.\n\n- Tests: failure\n"
    assert section in text
    assert text.index("### newest") < text.index("Versions are measured")


def test_the_summary_of_every_job_is_listed_under_checks_after_the_tables(tmp_path):
    _ok(tmp_path, "outdated", _finding())
    _job(
        tmp_path,
        "newest",
        None,
        {
            "result": "ok",
            "checked": 4,
            "issue": "alarm",
            "summary": (
                "tests and the live run passed on the newest versions\n"
                " allowed (pandas 3.1.1)"
            ),
        },
        "Prose.",
    )
    text = _render(tmp_path, "outdated newest")
    checks = (
        "### Checks\n\n- `newest`: tests and the live run passed on the newest "
        "versions allowed (pandas 3.1.1)\n"
    )
    assert checks in text
    assert text.index("### Packages") < text.index("### Checks")
    assert "Checks" not in _render(tmp_path, "outdated newest", issue="alarm")


def test_a_summary_alone_opens_no_issue(tmp_path):
    _job(tmp_path, "newest", None, {"result": "ok", "summary": "All fine."})
    assert _render(tmp_path, "newest") == ""


def test_the_summary_of_an_inconclusive_job_is_its_reason(tmp_path):
    _job(
        tmp_path,
        "newest",
        None,
        {"result": "inconclusive", "summary": "the live run hit a rate limit"},
    )
    text = _render(tmp_path, "newest")
    assert (
        "ran but could not prove anything, so its part of this report is "
        "missing. It says: the live run hit a rate limit" in text
    )
    assert "### Checks" not in text


def test_a_summary_that_is_no_string_is_an_error(tmp_path):
    _job(tmp_path, "newest", None, {"result": "ok", "summary": ["x"]})
    with pytest.raises(ValueError):
        report.load_results(tmp_path, ["newest"])


def test_a_section_alone_opens_the_issue(tmp_path):
    _job(tmp_path, "newest", None, {"result": "ok", "checked": 1}, "Something.\n")
    text = _render(tmp_path, "newest")
    assert text == "### newest\n\nSomething.\n"


def test_an_alarm_job_goes_to_the_alarm_and_not_to_the_report(tmp_path):
    _ok(tmp_path, "outdated", _finding())
    _job(
        tmp_path,
        "newest",
        [_finding(name="yfinance", current="1.8.0", newest="1.8.1")],
        {"result": "ok", "checked": 1, "issue": "alarm"},
        "The smoke run failed.",
    )
    text = _render(tmp_path, "outdated newest")
    assert "| `mcp` |" in text
    assert "yfinance" not in text and "smoke" not in text
    alarm = _render(tmp_path, "outdated newest", issue="alarm")
    assert "| `yfinance` | 1.8.0 | 1.8.1 | patch |" in alarm
    assert "### newest\n\nThe smoke run failed.\n" in alarm
    assert "mcp" not in alarm


def test_the_alarm_is_empty_when_its_jobs_have_nothing_to_say(tmp_path):
    _ok(tmp_path, "outdated", _finding())
    _job(tmp_path, "newest", None, {"result": "ok", "checked": 1, "issue": "alarm"})
    assert _render(tmp_path, "outdated newest", issue="alarm") == ""


def test_an_inconclusive_job_is_a_line_in_the_report_and_not_in_the_alarm(tmp_path):
    _job(tmp_path, "newest", None, {"result": "inconclusive", "issue": "alarm"})
    text = _render(tmp_path, "newest")
    assert "The job `newest` ran but could not prove anything" in text
    assert _render(tmp_path, "newest", issue="alarm") == ""


@pytest.mark.parametrize(
    ("statuses", "expected", "ready"),
    [
        ({"newest": {"result": "ok", "issue": "alarm"}}, "newest", True),
        ({"newest": {"result": "inconclusive", "issue": "alarm"}}, "newest", False),
        ({"newest": {"result": "failed", "issue": "alarm"}}, "newest", False),
        ({"images": {"result": "inconclusive"}}, "images", False),
        ({"images": {"result": "failed"}}, "images", True),
        ({}, "newest", False),
        ({"newest": {"result": "ok", "issue": "alarm"}}, "newest images", False),
    ],
)
def test_when_the_alarm_issue_may_be_touched(tmp_path, statuses, expected, ready):
    for job, status in statuses.items():
        _job(tmp_path, job, None, {"checked": 0} | status)
    loaded = report.load_results(tmp_path, expected.split())
    assert report.alarm_ready(loaded) is ready


def test_an_unknown_issue_is_an_error(tmp_path):
    _job(tmp_path, "newest", None, {"result": "ok", "issue": "news"})
    with pytest.raises(ValueError):
        report.load_results(tmp_path, ["newest"])


def test_the_script_writes_the_alarm_and_says_whether_it_is_ready(tmp_path):
    _job(
        tmp_path,
        "newest",
        None,
        {"result": "ok", "checked": 1, "issue": "alarm"},
        "The tests failed.",
    )
    output = tmp_path / "output.txt"
    env = os.environ | {
        "RESULTS": str(tmp_path),
        "EXPECTED": "newest",
        "REPORT": str(tmp_path / "out" / "report.md"),
        "ALARM": str(tmp_path / "out" / "alarm.md"),
        "GITHUB_OUTPUT": str(output),
    }
    run = subprocess.run(
        [sys.executable, str(FOLDER / "report.py")],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert (tmp_path / "out" / "report.md").read_text("utf-8") == ""
    assert "The tests failed." in (tmp_path / "out" / "alarm.md").read_text("utf-8")
    assert output.read_text("utf-8") == "alarm=ready\n"
    assert "ready for its issue" in run.stdout


def test_without_an_alarm_path_the_script_writes_the_report_alone(tmp_path):
    _ok(tmp_path, "outdated", _finding())
    output = tmp_path / "output.txt"
    env = os.environ | {
        "RESULTS": str(tmp_path),
        "EXPECTED": "outdated",
        "REPORT": str(tmp_path / "out" / "report.md"),
        "GITHUB_OUTPUT": str(output),
    }
    subprocess.run(
        [sys.executable, str(FOLDER / "report.py")],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["report.md"]
    assert not output.exists()


def test_a_switched_off_job_is_not_expected_and_leaves_the_report_empty(tmp_path):
    _ok(tmp_path, "outdated")
    assert _render(tmp_path, "outdated") == ""


def test_an_unexpected_artifact_is_read_as_well(tmp_path):
    _ok(tmp_path, "images", _finding(category="image", name="python"))
    assert "### Images" in _render(tmp_path, "")


def test_every_run_url_reaches_the_line(tmp_path):
    loaded = report.load_results(tmp_path, ["images"])
    text = report.render(loaded, [], False, "https://example.test/runs/1")
    assert "See [the run](https://example.test/runs/1)." in text


# --- untrusted values ---------------------------------------------------------


def test_values_from_a_registry_cannot_break_the_table(tmp_path):
    _ok(
        tmp_path,
        "images",
        _finding(category="image", name="evil|`name`", newest="1 |\n2"),
    )
    text = _render(tmp_path, "images")
    assert "| `evil\\|'name'` | 2.3.0 | 1 \\| 2 |" in text


# --- bad input ----------------------------------------------------------------


@pytest.mark.parametrize(
    "finding",
    [
        _finding(category="other"),
        _finding(where=[]),
        _finding(newest=""),
        _finding(category="vulnerability", newest=""),
        _finding(kind="huge"),
        _finding(scope="test"),
        _finding(direct="yes"),
        {"name": "mcp"},
    ],
)
def test_a_malformed_finding_is_an_error(finding):
    with pytest.raises(ValueError):
        report.parse_finding(finding)


def test_a_malformed_finding_fails_the_script(tmp_path):
    _ok(tmp_path, "outdated", _finding(category="other"))
    env = os.environ | {
        "RESULTS": str(tmp_path),
        "EXPECTED": "outdated",
        "REPORT": str(tmp_path / "report.md"),
    }
    run = subprocess.run(
        [sys.executable, str(FOLDER / "report.py")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1
    assert "::error::Could not read the findings" in run.stderr
    assert not (tmp_path / "report.md").exists()


def test_the_script_writes_the_report_and_names_each_job(tmp_path):
    _ok(tmp_path, "outdated", _finding())
    env = os.environ | {
        "RESULTS": str(tmp_path),
        "EXPECTED": "outdated images",
        "REPORT": str(tmp_path / "out" / "report.md"),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "example/repo",
        "GITHUB_RUN_ID": "42",
    }
    run = subprocess.run(
        [sys.executable, str(FOLDER / "report.py")],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "outdated: ok, 1 findings" in run.stdout
    assert "images: missing, 0 findings" in run.stdout
    text = (tmp_path / "out" / "report.md").read_text("utf-8")
    assert "https://github.com/example/repo/actions/runs/42" in text
    assert "| `mcp` |" in text


# --- the action and its format -----------------------------------------------


def test_the_action_takes_the_results_and_writes_the_report():
    assert set(ACTION["inputs"]) == {
        "results",
        "expected",
        "ignore",
        "dev",
        "report",
        "alarm",
    }
    assert ACTION["inputs"]["alarm"]["default"] == ""
    assert ACTION["outputs"]["alarm"]["value"] == "${{ steps.write.outputs.alarm }}"
    uv, run = ACTION["runs"]["steps"]
    assert uv["uses"].startswith("astral-sh/setup-uv@")
    # The report job has no checkout, so the empty working directory is no
    # news.
    assert uv["with"] == {"enable-cache": False, "ignore-empty-workdir": True}
    assert '"$GITHUB_ACTION_PATH/report.py"' in run["run"]
    assert run["id"] == "write"
    assert set(run["env"]) == {
        "RESULTS",
        "EXPECTED",
        "IGNORE",
        "DEV",
        "REPORT",
        "ALARM",
    }


def test_the_format_documents_every_field():
    for field in report.Finding.__dataclass_fields__:
        assert f"`{field}`" in FORMAT, field
    for key in (
        "result",
        "checked",
        "packages",
        "issue",
        "inconclusive",
        "section.md",
        "summary",
    ):
        assert f"`{key}`" in FORMAT
