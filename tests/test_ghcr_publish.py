"""The ghcr.io action: the check of the published index, the title step, and
how the action wires the Docker actions.

Pushing is left to a real release. The index check runs against an index in
the shape the registry returns.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION_DIR = ROOT / "actions" / "publish" / "ghcr"
ACTION = yaml.safe_load((ACTION_DIR / "action.yml").read_text("utf-8"))
STEPS = {step.get("name"): step for step in ACTION["runs"]["steps"]}

_spec = importlib.util.spec_from_file_location(
    "check_index", ACTION_DIR / "check_index.py"
)
assert _spec and _spec.loader
check_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_index)


def _index(platforms: list[str], annotations: dict[str, str] | None = None) -> dict:
    manifests = [
        {"platform": {"os": p.split("/")[0], "architecture": p.split("/")[1]}}
        for p in platforms
    ] + [{"platform": {"os": "unknown", "architecture": "unknown"}}]
    if annotations is None:
        annotations = {key: "set" for key in check_index.ANNOTATIONS}
    return {"manifests": manifests, "annotations": annotations}


def _main(tmp_path: Path, index: dict, platforms: str, monkeypatch) -> int:
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index), "utf-8")
    monkeypatch.setenv("PLATFORMS", platforms)
    return check_index.main([str(path)])


def test_an_index_with_every_platform_and_annotation_passes(
    tmp_path, monkeypatch, capsys
):
    index = _index(["linux/arm64", "linux/amd64"])
    assert _main(tmp_path, index, "linux/amd64,linux/arm64", monkeypatch) == 0
    assert "OK: linux/amd64, linux/arm64" in capsys.readouterr().out


def test_the_attestations_are_not_platforms():
    assert check_index.platforms_of(_index(["linux/amd64"])) == ["linux/amd64"]


def test_a_missing_platform_is_named(tmp_path, monkeypatch, capsys):
    assert (
        _main(tmp_path, _index(["linux/amd64"]), "linux/amd64,linux/arm64", monkeypatch)
        == 1
    )
    assert "::error::linux/arm64 is missing" in capsys.readouterr().out


def test_a_missing_annotation_is_named(tmp_path, monkeypatch, capsys):
    annotations = {
        "org.opencontainers.image.source": "x",
        "org.opencontainers.image.version": "1",
    }
    assert (
        _main(
            tmp_path, _index(["linux/amd64"], annotations), "linux/amd64", monkeypatch
        )
        == 1
    )
    assert "no org.opencontainers.image.description" in capsys.readouterr().out


def test_every_docker_action_is_pinned_to_a_commit():
    for step in ACTION["runs"]["steps"]:
        uses = step.get("uses", "")
        if uses.startswith("benethos-hub/"):
            continue
        if uses:
            assert re.fullmatch(r"[\w-]+/[\w-]+@[0-9a-f]{40}", uses), uses


def test_the_version_is_checked_on_a_release_only():
    first = ACTION["runs"]["steps"][1]
    assert first["if"] == "github.event_name == 'release'"
    assert (
        first["uses"] == "benethos-hub/.github/actions/release/tag-matches-version@main"
    )
    assert first["with"] == {"file": "${{ inputs.version-file }}"}


def test_latest_stays_on_the_last_full_release():
    tags = STEPS["Derive image tags, labels and annotations"]["with"]["tags"]
    assert (
        "type=raw,value=latest,enable=${{ github.event_name == 'release' "
        "&& !github.event.release.prerelease }}" in tags
    )
    assert (
        "type=raw,value=edge,enable=${{ github.event_name == 'workflow_dispatch' }}"
        in tags
    )


def test_each_image_has_its_own_build_cache():
    build = STEPS["Build and push"]["with"]
    assert build["cache-from"] == "type=gha,scope=${{ inputs.image }}"
    assert build["cache-to"] == "type=gha,mode=max,scope=${{ inputs.image }}"


@pytest.mark.skipif(sys.platform == "win32", reason="the step runs in bash")
@pytest.mark.parametrize(
    ("description", "lines"),
    [
        ("", []),
        (
            "Mailbox, mailbox-mcp: the MCP server.",
            [
                "org.opencontainers.image.title=benethos-example",
                "org.opencontainers.image.description="
                "Mailbox, mailbox-mcp: the MCP server.",
            ],
        ),
    ],
)
def test_an_own_description_becomes_title_and_description(tmp_path, description, lines):
    script = tmp_path / "step.sh"
    script.write_text(STEPS["Title and description of the image"]["run"])
    output = tmp_path / "output"
    env = {
        "PATH": "/usr/bin:/bin",
        "IMAGE": "benethos-example",
        "DESCRIPTION": description,
        "GITHUB_OUTPUT": str(output),
    }
    subprocess.run(["bash", str(script)], env=env, check=True)
    text = output.read_text()
    assert text.startswith("lines<<END_OF_LINES\n") and text.endswith("END_OF_LINES\n")
    assert text.splitlines()[1:-1] == lines


def test_the_image_tags_follow_the_version_scheme():
    """PEP 440 by default, so v1.0.0rc1 of a Python project gives an image tag.
    semver would give none for it, and the push would have nothing to push."""
    assert ACTION["inputs"]["version-scheme"]["default"] == "pep440"
    tags = STEPS["Derive image tags, labels and annotations"]["with"]["tags"]
    assert "type=${{ inputs.version-scheme }},pattern={{version}}" in tags
    assert "type=${{ inputs.version-scheme }},pattern={{major}}.{{minor}}" in tags


@pytest.mark.skipif(sys.platform == "win32", reason="the step runs in bash")
@pytest.mark.parametrize(
    ("scheme", "code"), [("pep440", 0), ("semver", 0), ("pep-440", 1), ("", 1)]
)
def test_an_unknown_version_scheme_stops_before_the_build(tmp_path, scheme, code):
    script = tmp_path / "step.sh"
    script.write_text(
        STEPS["The version scheme is one the image tags can follow"]["run"]
    )
    done = subprocess.run(
        ["bash", str(script)],
        env={"PATH": "/usr/bin:/bin", "SCHEME": scheme},
        capture_output=True,
        text=True,
    )
    assert done.returncode == code
    if code:
        assert "::error::version-scheme is" in done.stdout
