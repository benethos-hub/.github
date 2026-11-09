"""The Trivy misconfiguration scan: the script that builds the call, the action
with its pinned download, and the workflow around it.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

from scanner_wiring import (
    ROOT,
    assert_documented,
    assert_inputs_are_described,
    assert_installs_uv_first,
    assert_pinned_download,
    assert_reports_only_by_default,
    assert_reports_through_sarif_report,
    assert_workflow_mirrors_action,
    load,
    step,
)

ACTION_DIR = ROOT / "actions" / "trivy-config"
ACTION = load(ACTION_DIR / "action.yml")
WORKFLOW = load(ROOT / ".github" / "workflows" / "trivy-config.yml")
SARIF = "${{ runner.temp }}/trivy-config/trivy.sarif"

_spec = importlib.util.spec_from_file_location(
    "trivy_config", ACTION_DIR / "trivy_config.py"
)
assert _spec and _spec.loader
trivy_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trivy_config)

BASE = [
    "/t/trivy",
    "config",
    "--quiet",
    "--format",
    "sarif",
    "--output",
    "/o/t.sarif",
    "--exit-code",
    "0",
]


def test_the_bare_command_scans_the_folder_and_never_fails_on_a_finding():
    env = {"TRIVY": "/t/trivy", "OUT": "/o/t.sarif", "SCAN_PATH": "containers"}
    assert trivy_config.command(env) == [*BASE, "containers"]
    assert trivy_config.command({"OUT": "/o/t.sarif"}) == ["trivy", *BASE[1:], "."]


def test_every_option_goes_through_as_a_comma_list_and_offline_skips_the_update():
    env = {
        "TRIVY": "/t/trivy",
        "OUT": "/o/t.sarif",
        "CACHE_DIR": "/c",
        "SCANNERS": "dockerfile kubernetes",
        "SEVERITY": "HIGH CRITICAL",
        "SKIP_DIRS": "vendor",
        "SKIP_FILES": "a/* b",
        "IGNOREFILE": ".trivyignore",
        "CONFIG": "trivy.yaml",
        "CHECKS": "checks",
        "NAMESPACES": "user",
        "OFFLINE": "true",
        "SCAN_PATH": ".",
    }
    assert trivy_config.command(env) == [
        *BASE,
        "--cache-dir",
        "/c",
        "--misconfig-scanners",
        "dockerfile,kubernetes",
        "--severity",
        "HIGH,CRITICAL",
        "--skip-dirs",
        "vendor",
        "--skip-files",
        "a/*,b",
        "--ignorefile",
        ".trivyignore",
        "--config",
        "trivy.yaml",
        "--config-check",
        "checks",
        "--check-namespaces",
        "user",
        "--skip-check-update",
        ".",
    ]
    assert "--skip-check-update" not in trivy_config.command(
        {**env, "OFFLINE": "false"}
    )


def test_main_runs_trivy_and_needs_the_file_it_promised(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out" / "trivy.sarif"
    monkeypatch.setenv("OUT", str(out))
    monkeypatch.setenv("TRIVY", "/t/trivy")

    def writing_run(args, **kwargs):
        Path(args[args.index("--output") + 1]).write_text("{}", "utf-8")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(trivy_config.subprocess, "run", writing_run)
    assert trivy_config.main() == 0
    assert out.read_text("utf-8") == "{}"
    out.unlink()

    monkeypatch.setattr(
        trivy_config.subprocess,
        "run",
        lambda args, **k: subprocess.CompletedProcess(args, 0),
    )
    assert trivy_config.main() == 1
    assert "left no" in capsys.readouterr().out

    monkeypatch.setattr(
        trivy_config.subprocess,
        "run",
        lambda args, **k: subprocess.CompletedProcess(args, 2),
    )
    assert trivy_config.main() == 1
    assert "exit code 2" in capsys.readouterr().out


def test_the_action_downloads_trivy_pinned_scans_and_reports():
    assert_inputs_are_described(ACTION)
    assert ACTION["inputs"]["path"]["default"] == "."
    assert ACTION["inputs"]["offline"]["default"] == "false"
    assert_reports_only_by_default(ACTION)
    assert ACTION["inputs"]["category"]["default"] == "trivy-config"
    assert_installs_uv_first(ACTION)
    assert_pinned_download(
        ACTION, "Install trivy", "TRIVY_VERSION", "TRIVY_SHA256", "trivy"
    )
    install = step(ACTION, "Install trivy")
    assert "trivy_${TRIVY_VERSION#v}_Linux-64bit.tar.gz" in install["run"]
    assert "tar xzf" in install["run"]
    scan = step(ACTION, "Scan for misconfigurations")
    env = scan["env"]
    assert env["TRIVY"] == "${{ runner.temp }}/trivy/trivy"
    assert env["TRIVY_NO_PROGRESS"] == "true"
    assert env["OUT"] == SARIF
    assert env["CACHE_DIR"] == "${{ runner.temp }}/trivy-cache"
    for key, name in (
        ("SCAN_PATH", "path"),
        ("SCANNERS", "scanners"),
        ("SEVERITY", "severity"),
        ("SKIP_DIRS", "skip-dirs"),
        ("SKIP_FILES", "skip-files"),
        ("IGNOREFILE", "ignorefile"),
        ("CONFIG", "config"),
        ("CHECKS", "checks"),
        ("NAMESPACES", "namespaces"),
        ("OFFLINE", "offline"),
    ):
        assert env[key] == f"${{{{ inputs.{name} }}}}", key
    assert (
        'uv run --no-project --python ">=3.11" "$GITHUB_ACTION_PATH/trivy_config.py"'
        in scan["run"]
    )
    assert_reports_through_sarif_report(ACTION, SARIF, "Trivy")


def test_the_pin_matches_the_download_pins_entry_with_the_version_in_the_asset():
    pins = load(ROOT / ".github" / "download-pins.yml")
    (pin,) = [p for p in pins if p["name"] == "trivy"]
    assert pin == {
        "name": "trivy",
        "file": "actions/trivy-config/action.yml",
        "version": "TRIVY_VERSION",
        "sha256": "TRIVY_SHA256",
        "repository": "aquasecurity/trivy",
        "asset": "trivy_{version}_Linux-64bit.tar.gz",
        "checksums": "trivy_{version}_checksums.txt",
    }


def test_the_workflow_is_one_job_around_the_action():
    assert_workflow_mirrors_action(
        WORKFLOW,
        ACTION,
        "trivy-config",
        "Trivy config",
        "benethos-hub/.github/actions/trivy-config@main",
    )
    assert WORKFLOW[True]["workflow_call"]["inputs"]["offline"]["type"] == "boolean"


def test_the_documentation_names_every_input_and_the_files():
    page = (ROOT / "docs" / "dockerfile-checks.md").read_text("utf-8")
    assert_documented(
        ACTION,
        page,
        "../actions/trivy-config/action.yml",
        "../.github/workflows/trivy-config.yml",
    )
