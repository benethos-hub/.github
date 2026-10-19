"""The coverage badge: its script, and how python-tests.yml,
coverage-badge.yml and ci.yml wire it. The action and the workflow are the
same for every language, only python-tests.yml knows coverage.py.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION_DIR = ROOT / "actions" / "coverage-badge"
ACTION = yaml.safe_load((ACTION_DIR / "action.yml").read_text("utf-8"))
TESTS = yaml.safe_load(
    (ROOT / ".github" / "workflows" / "python-tests.yml").read_text("utf-8")
)
BADGE = yaml.safe_load(
    (ROOT / ".github" / "workflows" / "coverage-badge.yml").read_text("utf-8")
)
CI = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8"))

_spec = importlib.util.spec_from_file_location("badge", ACTION_DIR / "badge.py")
assert _spec and _spec.loader
badge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(badge)


# The script.


@pytest.mark.parametrize(
    ("percent", "message", "color"),
    [
        (100, "100%", "brightgreen"),
        (90.0, "90%", "brightgreen"),
        (89.9, "89%", "green"),
        (80.4, "80%", "green"),
        (79.9, "79%", "yellowgreen"),
        (65, "65%", "yellow"),
        (55, "55%", "orange"),
        (49.99, "49%", "red"),
        (0, "0%", "red"),
    ],
)
def test_the_badge_rounds_down_and_colours_by_the_usual_scale(percent, message, color):
    assert badge.badge(percent) == {
        "schemaVersion": 1,
        "label": "coverage",
        "message": message,
        "color": color,
    }


def test_main_takes_a_percentage_and_writes_the_badge(tmp_path, capsys):
    target = tmp_path / "badge" / "coverage.json"
    assert badge.main(["91.3", str(target)]) == 0
    assert json.loads(target.read_text("utf-8"))["message"] == "91%"
    assert target.read_text("utf-8").endswith("\n")
    assert "coverage 91.3%, badge 91% brightgreen" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["", "abc", "nan", "-1", "100.5"])
def test_anything_but_a_percentage_is_an_error(tmp_path, capsys, value):
    assert badge.main([value, str(tmp_path / "out.json")]) == 1
    assert "::error::" in capsys.readouterr().out
    assert not (tmp_path / "out.json").exists()


def test_a_wrong_call_prints_the_usage(capsys):
    assert badge.main([]) == 2
    assert "badge.py <percent> <badge.json>" in capsys.readouterr().err


# The wiring.


def test_the_tests_read_the_percentage_and_upload_it_on_the_coverage_version():
    assert TESTS[True]["workflow_call"]["inputs"]["badge"]["default"] is False
    steps = {s.get("name"): s for s in TESTS["jobs"]["test"]["steps"]}
    read = steps["Read the measured coverage"]
    write = steps["Write the coverage badge"]
    upload = steps["Upload it for coverage-badge.yml"]
    for step in (read, write, upload):
        assert step["if"] == (
            "inputs.badge && matrix.python-version == inputs.coverage-python"
        )
    assert read["id"] == "coverage"
    assert (
        'uv run --frozen coverage json -o "$RUNNER_TEMP/coverage.json"' in read["run"]
    )
    assert "jq -r .totals.percent_covered" in read["run"]
    assert write["uses"] == "benethos-hub/.github/actions/coverage-badge@main"
    assert write["with"]["percent"] == "${{ steps.coverage.outputs.percent }}"
    assert write["with"]["badge-json"] == upload["with"]["path"]
    assert (
        upload["with"]["name"]
        == BADGE[True]["workflow_call"]["inputs"]["artifact"]["default"]
    )


def test_the_action_knows_no_language():
    """It takes a percentage, so a test workflow of any language can use it."""
    assert set(ACTION["inputs"]) == {"percent", "badge-json"}
    uv, step = ACTION["runs"]["steps"]
    assert uv["uses"].startswith("astral-sh/setup-uv@")
    assert '"$GITHUB_ACTION_PATH/badge.py" "$PERCENT" "$BADGE_JSON"' in step["run"]


def test_the_badge_workflow_may_push_the_branch():
    assert BADGE["permissions"] == {"contents": "write"}
    assert BADGE[True]["workflow_call"]["inputs"]["branch"]["default"] == "badges"
    (job,) = BADGE["jobs"].values()
    assert job["name"] == "Coverage badge"
    download, publish = job["steps"][1], job["steps"][2]
    assert download["uses"].startswith("actions/download-artifact@")
    assert download["with"]["name"] == "${{ inputs.artifact }}"
    assert 'git push --quiet origin "HEAD:$BRANCH"' in publish["run"]
    assert "git checkout --quiet --orphan" in publish["run"]


def test_this_repository_publishes_its_own_badge_on_a_push():
    assert CI["jobs"]["test"]["with"] == {"badge": True}
    job = CI["jobs"]["coverage-badge"]
    assert job["if"] == "github.event_name == 'push'"
    assert job["needs"] == "test"
    assert job["uses"] == "./.github/workflows/coverage-badge.yml"
    assert job["permissions"] == {"contents": "write"}
