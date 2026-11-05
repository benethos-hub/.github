"""The Dockerfile lint: the script that finds the files and calls hadolint, the
action with its pinned download, and the workflow around it.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from scanner_wiring import (
    ROOT,
    assert_documented,
    assert_inputs_are_described,
    assert_installs_uv_first,
    assert_pinned_download,
    assert_reports_through_sarif_report,
    assert_workflow_mirrors_action,
    load,
    step,
)

ACTION_DIR = ROOT / "actions" / "dockerfile-lint"
ACTION = load(ACTION_DIR / "action.yml")
WORKFLOW = load(ROOT / ".github" / "workflows" / "dockerfile-lint.yml")
SARIF = "${{ runner.temp }}/dockerfile-lint/hadolint.sarif"

_spec = importlib.util.spec_from_file_location(
    "dockerfile_lint", ACTION_DIR / "dockerfile_lint.py"
)
assert _spec and _spec.loader
dockerfile_lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dockerfile_lint)


def _tree(tmp_path: Path) -> Path:
    for name in (
        "Dockerfile",
        "containers/images/a/Dockerfile",
        "containers/images/b/Dockerfile.dev",
        ".git/Dockerfile",
        "docs/Dockerfile.md",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("FROM scratch\n", "utf-8")
    (tmp_path / "containers" / "Dockerfile").mkdir()
    return tmp_path


def test_the_files_are_found_by_pattern_sorted_and_without_git(tmp_path):
    root = _tree(tmp_path)
    assert dockerfile_lint.find_files(root, ["**/Dockerfile*"]) == [
        "Dockerfile",
        "containers/images/a/Dockerfile",
        "containers/images/b/Dockerfile.dev",
        "docs/Dockerfile.md",
    ]
    assert dockerfile_lint.find_files(root, ["containers/**/Dockerfile"]) == [
        "containers/images/a/Dockerfile"
    ]
    assert dockerfile_lint.find_files(root, ["Dockerfile", "Dockerfile"]) == [
        "Dockerfile"
    ]
    assert dockerfile_lint.find_files(root, ["nothing/*"]) == []


def test_the_command_passes_every_option_and_leaves_the_verdict_to_the_report():
    assert dockerfile_lint.command("/t/hadolint", ["a/Dockerfile"], [], [], "") == [
        "/t/hadolint",
        "--no-fail",
        "--no-color",
        "--format",
        "sarif",
        "--",
        "a/Dockerfile",
    ]
    full = dockerfile_lint.command(
        "hadolint",
        ["x", "y"],
        ["DL3025", "DL3066"],
        ["docker.io", "ghcr.io"],
        ".hadolint.yaml",
    )
    assert full[5:] == [
        "--ignore",
        "DL3025",
        "--ignore",
        "DL3066",
        "--trusted-registry",
        "docker.io",
        "--trusted-registry",
        "ghcr.io",
        "--config",
        ".hadolint.yaml",
        "--",
        "x",
        "y",
    ]


def test_without_a_file_an_empty_sarif_is_left_and_nothing_fails(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out" / "hadolint.sarif"
    monkeypatch.setenv("OUT", str(out))
    monkeypatch.setenv("FILES", "containers/**/Dockerfile")
    monkeypatch.setenv("HADOLINT", str(tmp_path / "missing"))
    assert dockerfile_lint.main() == 0
    sarif = json.loads(out.read_text("utf-8"))
    assert sarif["runs"] == [{"tool": {"driver": {"name": "Hadolint"}}, "results": []}]
    assert (
        "::notice::No file matches containers/**/Dockerfile" in capsys.readouterr().out
    )


def test_the_output_of_hadolint_is_written_and_its_failure_is_an_error(
    tmp_path, monkeypatch, capsys
):
    root = _tree(tmp_path)
    monkeypatch.chdir(root)
    out = root / "out" / "hadolint.sarif"
    monkeypatch.setenv("OUT", str(out))
    monkeypatch.setenv("FILES", "Dockerfile")
    monkeypatch.setenv("HADOLINT", "/t/hadolint")
    monkeypatch.setenv("IGNORE", "DL3025")
    monkeypatch.setenv("TRUSTED_REGISTRIES", "")
    monkeypatch.setenv("CONFIG", "")
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout='{"runs": []}', stderr="")

    monkeypatch.setattr(dockerfile_lint.subprocess, "run", fake_run)
    assert dockerfile_lint.main() == 0
    assert calls == [
        [
            "/t/hadolint",
            "--no-fail",
            "--no-color",
            "--format",
            "sarif",
            "--ignore",
            "DL3025",
            "--",
            "Dockerfile",
        ]
    ]
    assert out.read_text("utf-8") == '{"runs": []}'
    assert "hadolint read 1 file." in capsys.readouterr().out

    def failing_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="cannot parse")

    monkeypatch.setattr(dockerfile_lint.subprocess, "run", failing_run)
    assert dockerfile_lint.main() == 1
    assert "::error::hadolint failed: cannot parse" in capsys.readouterr().out


def test_the_action_downloads_hadolint_pinned_lints_and_reports():
    assert_inputs_are_described(ACTION)
    assert ACTION["inputs"]["files"]["default"] == "**/Dockerfile*"
    assert ACTION["inputs"]["failure-level"]["default"] == "warning"
    assert ACTION["inputs"]["category"]["default"] == "dockerfile-lint"
    assert_installs_uv_first(ACTION)
    assert_pinned_download(
        ACTION, "Install hadolint", "HADOLINT_VERSION", "HADOLINT_SHA256", "hadolint"
    )
    install = step(ACTION, "Install hadolint")
    assert "hadolint-linux-x86_64" in install["run"]
    assert "chmod +x" in install["run"]
    lint = step(ACTION, "Lint the Dockerfiles")
    assert lint["env"] == {
        "HADOLINT": "${{ runner.temp }}/hadolint/hadolint",
        "FILES": "${{ inputs.files }}",
        "IGNORE": "${{ inputs.ignore }}",
        "TRUSTED_REGISTRIES": "${{ inputs.trusted-registries }}",
        "CONFIG": "${{ inputs.config }}",
        "OUT": SARIF,
    }
    assert (
        'uv run --no-project --python ">=3.11" "$GITHUB_ACTION_PATH/dockerfile_lint.py"'
        in lint["run"]
    )
    assert_reports_through_sarif_report(ACTION, SARIF, "hadolint")


def test_the_pin_matches_the_download_pins_entry():
    pins = load(ROOT / ".github" / "download-pins.yml")
    (pin,) = [p for p in pins if p["name"] == "hadolint"]
    assert pin == {
        "name": "hadolint",
        "file": "actions/dockerfile-lint/action.yml",
        "version": "HADOLINT_VERSION",
        "sha256": "HADOLINT_SHA256",
        "repository": "hadolint/hadolint",
        "asset": "hadolint-linux-x86_64",
        "checksums": "checksums.sha256",
    }


def test_the_workflow_is_one_job_around_the_action():
    assert_workflow_mirrors_action(
        WORKFLOW,
        ACTION,
        "dockerfile-lint",
        "Dockerfile lint",
        "benethos-hub/.github/actions/dockerfile-lint@main",
    )
    assert WORKFLOW[True]["workflow_call"]["inputs"]["timeout-minutes"]["default"] == 10


def test_the_documentation_names_every_input_and_the_files():
    page = (ROOT / "docs" / "dockerfile-checks.md").read_text("utf-8")
    assert_documented(
        ACTION,
        page,
        "../actions/dockerfile-lint/action.yml",
        "../.github/workflows/dockerfile-lint.yml",
    )
