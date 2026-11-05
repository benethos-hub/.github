"""The Checkov scan: the script that builds the call through the lockfile, the
action, its locked project, and the workflow around it.
"""

from __future__ import annotations

import importlib.util
import subprocess
import tomllib
from pathlib import Path

from scanner_wiring import (
    ROOT,
    assert_documented,
    assert_inputs_are_described,
    assert_installs_uv_first,
    assert_reports_through_sarif_report,
    assert_workflow_mirrors_action,
    load,
    step,
)

ACTION_DIR = ROOT / "actions" / "checkov"
ACTION = load(ACTION_DIR / "action.yml")
WORKFLOW = load(ROOT / ".github" / "workflows" / "checkov.yml")
SARIF = "${{ runner.temp }}/checkov/results_sarif.sarif"

_spec = importlib.util.spec_from_file_location(
    "checkov_scan", ACTION_DIR / "checkov_scan.py"
)
assert _spec and _spec.loader
checkov_scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checkov_scan)

BASE = [
    "uv",
    "run",
    "--quiet",
    "--frozen",
    "--project",
    "/a",
    "checkov",
    "--directory",
    ".",
    "--skip-download",
    "--soft-fail",
    "--quiet",
    "--compact",
    "--output",
    "cli",
    "--output",
    "sarif",
    "--output-file-path",
    "/o",
]


def test_the_bare_command_runs_from_the_lockfile_and_never_fails_on_a_finding():
    assert checkov_scan.command({"ACTION_PATH": "/a", "OUT_DIR": "/o"}) == BASE
    with_dir = checkov_scan.command(
        {
            "ACTION_PATH": "/a",
            "OUT_DIR": "/o",
            "DIRECTORY": "containers",
            "FRAMEWORK": "dockerfile",
        }
    )
    assert with_dir[7:9] == ["--directory", "containers"]
    assert with_dir[-2:] == ["--framework", "dockerfile"]


def test_every_option_goes_through_in_the_form_checkov_takes():
    env = {
        "ACTION_PATH": "/a",
        "OUT_DIR": "/o",
        "FRAMEWORK": "dockerfile kubernetes",
        "CHECK": "CKV_DOCKER_2 CKV_DOCKER_3",
        "SKIP_CHECK": "CKV_DOCKER_7, CKV_DOCKER_8",
        "SKIP_PATH": "vendor tests/fixtures",
        "CONFIG_FILE": ".checkov.yaml",
        "EXTERNAL_CHECKS": "checks",
    }
    assert checkov_scan.command(env)[len(BASE) :] == [
        "--framework",
        "dockerfile",
        "kubernetes",
        "--check",
        "CKV_DOCKER_2,CKV_DOCKER_3",
        "--skip-check",
        "CKV_DOCKER_7,CKV_DOCKER_8",
        "--skip-path",
        "vendor",
        "--skip-path",
        "tests/fixtures",
        "--config-file",
        ".checkov.yaml",
        "--external-checks-dir",
        "checks",
    ]


def test_main_runs_checkov_and_needs_the_sarif_it_promised(
    tmp_path, monkeypatch, capsys
):
    out_dir = tmp_path / "out"
    monkeypatch.setenv("OUT_DIR", str(out_dir))
    monkeypatch.setenv("ACTION_PATH", str(ACTION_DIR))

    def writing_run(args, **kwargs):
        Path(
            args[args.index("--output-file-path") + 1], "results_sarif.sarif"
        ).write_text("{}", "utf-8")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(checkov_scan.subprocess, "run", writing_run)
    assert checkov_scan.main() == 0
    assert (out_dir / "results_sarif.sarif").read_text("utf-8") == "{}"
    (out_dir / "results_sarif.sarif").unlink()

    monkeypatch.setattr(
        checkov_scan.subprocess,
        "run",
        lambda args, **k: subprocess.CompletedProcess(args, 0),
    )
    assert checkov_scan.main() == 1
    assert "left no results_sarif.sarif" in capsys.readouterr().out

    monkeypatch.setattr(
        checkov_scan.subprocess,
        "run",
        lambda args, **k: subprocess.CompletedProcess(args, 3),
    )
    assert checkov_scan.main() == 1
    assert "exit code 3" in capsys.readouterr().out


def test_checkov_is_locked_next_to_the_action_and_is_no_package():
    project = tomllib.loads((ACTION_DIR / "pyproject.toml").read_text("utf-8"))
    assert project["tool"]["uv"]["package"] is False
    assert project["project"]["requires-python"] == ">=3.11"
    (dependency,) = project["project"]["dependencies"]
    assert dependency.startswith("checkov>=")
    lock = (ACTION_DIR / "uv.lock").read_text("utf-8")
    assert '\nname = "checkov"\n' in lock


def test_the_action_scans_from_the_lockfile_and_reports():
    assert_inputs_are_described(ACTION)
    assert ACTION["inputs"]["directory"]["default"] == "."
    assert ACTION["inputs"]["framework"]["default"] == "dockerfile"
    assert ACTION["inputs"]["failure-level"]["default"] == "error"
    assert ACTION["inputs"]["category"]["default"] == "checkov"
    assert_installs_uv_first(ACTION)
    scan = step(ACTION, "Scan with Checkov")
    env = scan["env"]
    assert env["ACTION_PATH"] == "${{ github.action_path }}"
    assert env["UV_PROJECT_ENVIRONMENT"] == "${{ runner.temp }}/checkov-env"
    assert env["OUT_DIR"] == "${{ runner.temp }}/checkov"
    for key, name in (
        ("DIRECTORY", "directory"),
        ("FRAMEWORK", "framework"),
        ("CHECK", "check"),
        ("SKIP_CHECK", "skip-check"),
        ("SKIP_PATH", "skip-path"),
        ("CONFIG_FILE", "config-file"),
        ("EXTERNAL_CHECKS", "external-checks"),
    ):
        assert env[key] == f"${{{{ inputs.{name} }}}}", key
    assert (
        'uv run --no-project --python ">=3.11" "$GITHUB_ACTION_PATH/checkov_scan.py"'
        in scan["run"]
    )
    assert_reports_through_sarif_report(ACTION, SARIF, "Checkov")


def test_the_workflow_is_one_job_around_the_action():
    assert_workflow_mirrors_action(
        WORKFLOW,
        ACTION,
        "checkov",
        "Checkov",
        "benethos-hub/.github/actions/checkov@main",
    )
    assert WORKFLOW[True]["workflow_call"]["inputs"]["timeout-minutes"]["default"] == 15


def test_the_documentation_names_every_input_and_the_files():
    page = (ROOT / "docs" / "dockerfile-checks.md").read_text("utf-8")
    assert_documented(
        ACTION,
        page,
        "../actions/checkov/action.yml",
        "../.github/workflows/checkov.yml",
    )
