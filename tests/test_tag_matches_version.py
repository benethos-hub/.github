"""The check that a release tag is the version it publishes.

It runs in every publishing job of every repository, against a pyproject.toml
or against the JSON of a bundle manifest or a registry entry.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION_DIR = ROOT / "actions" / "release" / "tag-matches-version"
ACTION = yaml.safe_load((ACTION_DIR / "action.yml").read_text("utf-8"))

_spec = importlib.util.spec_from_file_location(
    "tag_matches_version", ACTION_DIR / "tag_matches_version.py"
)
assert _spec and _spec.loader
tmv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tmv)


def _pyproject(tmp_path: Path, version: str = "1.2.3") -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "example"\nversion = "{version}"\n', "utf-8")
    return path


def _json(tmp_path: Path, name: str, version: str = "1.2.3") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"name": "example", "version": version}), "utf-8")
    return path


@pytest.mark.parametrize("tag", ["v1.2.3", "1.2.3"])
def test_a_matching_tag_passes(tmp_path, tag, capsys):
    assert tmv.check(tag, _pyproject(tmp_path)) == 0
    assert "matches the version 1.2.3" in capsys.readouterr().out


def test_a_tag_ahead_of_the_version_stops_the_release(tmp_path, capsys):
    assert tmv.check("v1.3.0", _pyproject(tmp_path)) == 1
    out = capsys.readouterr().out
    assert out.startswith("::error::Release tag 'v1.3.0' is not the version '1.2.3'")
    assert "or tag v1.2.3" in out


@pytest.mark.parametrize("name", ["manifest.json", "server.json"])
def test_a_json_file_counts_with_its_top_level_version(tmp_path, name):
    assert tmv.check("v1.2.3", _json(tmp_path, name)) == 0
    assert tmv.check("v1.2.4", _json(tmp_path, name)) == 1


def test_a_file_without_a_version_is_named(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "example"\ndynamic = ["version"]\n', "utf-8")
    with pytest.raises(SystemExit, match="has no \\[project\\] version"):
        tmv.check("v1.2.3", path)


def test_another_kind_of_file_is_refused(tmp_path):
    path = tmp_path / "setup.cfg"
    path.write_text("[metadata]\nversion = 1.2.3\n", "utf-8")
    with pytest.raises(SystemExit, match="neither a .toml nor a .json"):
        tmv.check("v1.2.3", path)


def test_main_reads_the_tag_and_the_file_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TAG", "v2.0.0")
    monkeypatch.setenv("VERSION_FILE", str(_json(tmp_path, "server.json", "2.0.0")))
    assert tmv.main() == 0


def test_without_a_tag_the_release_stops(monkeypatch, capsys):
    monkeypatch.setenv("TAG", "")
    assert tmv.main() == 1
    assert "::error::No release tag" in capsys.readouterr().out


def test_the_action_runs_the_script_from_its_own_folder_with_the_release_tag():
    uv, step = ACTION["runs"]["steps"]
    assert uv["uses"].startswith("astral-sh/setup-uv@")
    assert "uv run --no-project" in step["run"]
    assert '"$GITHUB_ACTION_PATH/tag_matches_version.py"' in step["run"]
    assert step["env"]["TAG"] == (
        "${{ inputs.tag || github.event.release.tag_name || github.ref_name }}"
    )
    assert step["env"]["VERSION_FILE"] == "${{ inputs.file }}"
    assert ACTION["inputs"]["file"]["default"] == "pyproject.toml"
