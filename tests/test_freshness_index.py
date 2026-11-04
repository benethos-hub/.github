"""The index job of the freshness workflow: what the package installed from
the index says for the report, from the outcomes the action measured.
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
FOLDER = ROOT / "actions" / "python" / "freshness-index"
ACTION = yaml.safe_load((FOLDER / "action.yml").read_text("utf-8"))

_spec = importlib.util.spec_from_file_location("freshness_index", FOLDER / "index.py")
assert _spec and _spec.loader
index = importlib.util.module_from_spec(_spec)
sys.modules["freshness_index"] = index
_spec.loader.exec_module(index)

FREEZE = """\
benethos-example==0.12.0
mcp==2.3.0
numpy==2.5.4
pandas==3.1.1
yfinance==1.8.0
"""

SHOW = """\
Name: benethos-example
Version: 0.12.0
Location: /tmp/venv/lib/python3.15/site-packages
Requires: mcp, pandas, yfinance
Required-by:
"""

VERSIONS = index.parse_freeze(FREEZE)
SHOWN = index.parse_show(SHOW)


def _outcome(install_exit=0, check_exit=0, check="x --version", rate_limit=3):
    return index.outcome(
        "benethos-example", install_exit, VERSIONS, SHOWN, check, check_exit, rate_limit
    )


# --- what uv said -------------------------------------------------------------


def test_the_name_comes_from_the_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example-mcp"\n', "utf-8"
    )
    assert index.project_name(tmp_path / "pyproject.toml") == "example-mcp"


def test_a_workspace_root_without_a_project_asks_for_the_name(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["a"]\n', "utf-8"
    )
    with pytest.raises(ValueError, match="Name the package"):
        index.project_name(tmp_path / "pyproject.toml")
    with pytest.raises(ValueError, match="does not exist"):
        index.project_name(tmp_path / "nowhere.toml")


def test_freeze_and_show_are_read():
    assert VERSIONS == {
        "benethos-example": "0.12.0",
        "mcp": "2.3.0",
        "numpy": "2.5.4",
        "pandas": "3.1.1",
        "yfinance": "1.8.0",
    }
    assert SHOWN == index.Shown("0.12.0", ("mcp", "pandas", "yfinance"))


# --- the outcomes -------------------------------------------------------------


def test_a_passed_check_is_a_summary_with_the_direct_versions():
    found = _outcome()
    assert found.result == "ok"
    assert found.section == ""
    assert found.checked == 5
    assert found.summary == (
        "0.12.0 from the index passes its check with mcp 2.3.0, pandas 3.1.1, "
        "yfinance 1.8.0"
    )


def test_a_failed_installation_is_a_finding_for_the_alarm():
    found = _outcome(install_exit=1)
    assert found.result == "ok"
    assert found.summary == ""
    assert "`benethos-example` could not be installed from the index" in found.section
    assert "exit code 1" in found.section
    assert found.checked == 0


def test_a_rate_limit_is_inconclusive_with_the_reason():
    found = _outcome(check_exit=3)
    assert found.result == "inconclusive"
    assert found.section == ""
    assert found.summary == (
        "the check of 0.12.0 from the index hit a rate limit, exit code 3"
    )


def test_a_failed_check_is_a_section_with_the_resolved_packages():
    found = _outcome(check_exit=1, check="$FRESHNESS_PYTHON tests/smoke.py")
    assert found.result == "ok"
    assert found.summary == ""
    assert "`benethos-example` 0.12.0 from the index fails its check" in found.section
    assert "- Check: `$FRESHNESS_PYTHON tests/smoke.py`, exit code 1" in found.section
    assert "| `pandas` | 3.1.1 |" in found.section
    assert "benethos-example` | 0.12.0" not in found.section


def test_without_a_check_the_installation_alone_is_the_summary():
    found = _outcome(check_exit=None)
    assert found.result == "ok"
    assert found.summary.startswith("0.12.0 from the index installs with mcp 2.3.0")


# --- the script ---------------------------------------------------------------


def _write(tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "freeze.txt").write_text(FREEZE, "utf-8")
    (tmp_path / "show.txt").write_text(SHOW, "utf-8")
    return subprocess.run(
        [sys.executable, str(FOLDER / "index.py"), "write"],
        env=os.environ
        | {
            "PACKAGE": "benethos-example",
            "INSTALL_EXIT": "0",
            "FREEZE": str(tmp_path / "freeze.txt"),
            "SHOW": str(tmp_path / "show.txt"),
            "CHECK": "x --version",
            "CHECK_EXIT": "0",
            "RATE_LIMIT_EXIT": "3",
            "FINDINGS": str(tmp_path / "out"),
        }
        | env,
        capture_output=True,
        text=True,
    )


def test_the_script_writes_the_status_for_the_alarm(tmp_path):
    run = _write(tmp_path)
    assert run.returncode == 0, run.stderr
    status = json.loads((tmp_path / "out" / "status.json").read_text("utf-8"))
    assert status == {
        "result": "ok",
        "checked": 5,
        "issue": "alarm",
        "summary": (
            "0.12.0 from the index passes its check with mcp 2.3.0, pandas 3.1.1, "
            "yfinance 1.8.0"
        ),
    }
    assert not (tmp_path / "out" / "section.md").exists()
    assert "index: ok, 0.12.0 from the index passes" in run.stdout


def test_the_script_writes_the_section_on_a_failure(tmp_path):
    run = _write(tmp_path, CHECK_EXIT="1")
    assert run.returncode == 0, run.stderr
    status = json.loads((tmp_path / "out" / "status.json").read_text("utf-8"))
    assert status == {"result": "ok", "checked": 5, "issue": "alarm"}
    assert "fails its check" in (tmp_path / "out" / "section.md").read_text("utf-8")


def test_the_script_prints_the_name_of_the_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example-mcp"\n', "utf-8"
    )
    run = subprocess.run(
        [sys.executable, str(FOLDER / "index.py"), "name"],
        env=os.environ | {"ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0 and run.stdout.strip() == "example-mcp"


def test_a_root_without_a_name_fails_the_script(tmp_path):
    run = subprocess.run(
        [sys.executable, str(FOLDER / "index.py"), "name"],
        env=os.environ | {"ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1
    assert "::error::" in run.stderr


# --- the action ---------------------------------------------------------------


def test_the_action_installs_into_a_fresh_environment_and_hands_it_to_the_check():
    assert set(ACTION["inputs"]) == {
        "findings",
        "package",
        "check",
        "rate-limit-exit-code",
        "python",
    }
    assert ACTION["inputs"]["rate-limit-exit-code"]["default"] == "3"
    (run,) = [s for s in ACTION["runs"]["steps"] if "run" in s]
    script = run["run"]
    assert 'uv venv --quiet ${python[@]+"${python[@]}"} "$venv"' in script
    assert 'uv pip install --python "$venv" "$package" || install_exit=$?' in script
    assert 'uv pip freeze --python "$venv"' in script
    assert 'uv pip show --python "$venv" "$package"' in script
    assert 'check="\\"$venv/bin/$package\\" --version"' in script
    assert 'export FRESHNESS_PYTHON="$venv/bin/python"' in script
    assert 'bash -c "$check" || check_exit=$?' in script
    assert '"$GITHUB_ACTION_PATH/index.py" name' in script
    assert '"$GITHUB_ACTION_PATH/index.py" write' in script
    assert set(run["env"]) == {
        "PACKAGE",
        "CHECK",
        "RATE_LIMIT_EXIT",
        "PYTHON",
        "FINDINGS",
        "WORK",
    }
