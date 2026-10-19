"""The PyPI action: the check of what was built, and how the action wires it.

A version on PyPI cannot be replaced, so the check runs against wheels built
here in the shape uv writes them.
"""

from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION_DIR = ROOT / "actions" / "publish" / "pypi"
ACTION = yaml.safe_load((ACTION_DIR / "action.yml").read_text("utf-8"))
STEPS = {step.get("name"): step for step in ACTION["runs"]["steps"]}

_spec = importlib.util.spec_from_file_location("check_dist", ACTION_DIR / "check_dist.py")
assert _spec and _spec.loader
check_dist = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_dist)

FILES = [
    "benethos_example/__init__.py",
    "benethos_example/py.typed",
    "benethos_example-1.2.3.dist-info/licenses/LICENSE",
]


def _dist(tmp_path: Path, name: str = "benethos_example", version: str = "1.2.3", files: list[str] = FILES) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    with zipfile.ZipFile(dist / f"{name}-{version}-py3-none-any.whl", "w") as wheel:
        for path in files:
            wheel.writestr(path, "")
    (dist / f"{name}-{version}.tar.gz").write_bytes(b"")
    return dist


def test_the_release_passes(tmp_path, capsys):
    contains = ["benethos_example/py.typed", "benethos_example-{version}.dist-info/licenses/LICENSE"]
    assert check_dist.check(_dist(tmp_path), "v1.2.3", "benethos-example", contains) == 0
    assert capsys.readouterr().out.startswith("OK: benethos_example-1.2.3-py3-none-any.whl")


def test_a_wheel_of_another_version_is_not_uploaded(tmp_path, capsys):
    assert check_dist.check(_dist(tmp_path), "v1.3.0", "", []) == 1
    assert "is version 1.2.3, the release tag is v1.3.0" in capsys.readouterr().out


def test_a_missing_file_is_named(tmp_path, capsys):
    dist = _dist(tmp_path, files=["benethos_example/__init__.py"])
    assert check_dist.check(dist, "v1.2.3", "", ["benethos_example/py.typed"]) == 1
    assert "does not contain benethos_example/py.typed" in capsys.readouterr().out


def test_another_member_of_the_workspace_is_refused(tmp_path, capsys):
    assert check_dist.check(_dist(tmp_path), "v1.2.3", "benethos-other", []) == 1
    assert "is not the package benethos-other" in capsys.readouterr().out


@pytest.mark.parametrize("extra", ["benethos_other-1.2.3-py3-none-any.whl", None])
def test_exactly_one_wheel_and_one_sdist(tmp_path, extra, capsys):
    dist = _dist(tmp_path)
    if extra:
        (dist / extra).write_bytes(b"")
    else:
        next(dist.glob("*.tar.gz")).unlink()
    assert check_dist.check(dist, "v1.2.3", "", []) == 1
    assert "Expected one wheel and one sdist" in capsys.readouterr().out


def test_main_reads_its_settings_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DIST", str(_dist(tmp_path)))
    monkeypatch.setenv("TAG", "v1.2.3")
    monkeypatch.setenv("PACKAGE", "")
    monkeypatch.setenv("WHEEL_CONTAINS", "\n  benethos_example/py.typed\n\n")
    assert check_dist.main() == 0
    monkeypatch.setenv("WHEEL_CONTAINS", "benethos_example/missing.txt")
    assert check_dist.main() == 1


def test_the_action_builds_checks_and_uploads_from_one_folder():
    build = STEPS["Build sdist and wheel"]
    check = STEPS["The wheel is the release and carries what it should"]
    upload = STEPS["Publish to PyPI (Trusted Publishing)"]
    assert build["env"]["DIST"] == check["env"]["DIST"] == upload["env"]["DIST"]
    assert 'rm -rf "$DIST"' in build["run"] and '--package "$PACKAGE"' in build["run"]
    assert '"$GITHUB_ACTION_PATH/check_dist.py"' in check["run"]
    assert upload["run"] == 'uv publish --trusted-publishing always "$DIST"/*'
    assert check["env"]["TAG"] == "${{ inputs.tag || github.event.release.tag_name || github.ref_name }}"


def test_a_trial_run_checks_everything_but_the_version(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DIST", str(_dist(tmp_path)))
    monkeypatch.setenv("TAG", "main")
    monkeypatch.setenv("PACKAGE", "")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("WHEEL_CONTAINS", "benethos_example/py.typed")
    assert check_dist.main() == 0
    assert "Trial run: benethos_example-1.2.3-py3-none-any.whl is version 1.2.3" in capsys.readouterr().out
    monkeypatch.setenv("WHEEL_CONTAINS", "benethos_example/missing.txt")
    assert check_dist.main() == 1


def test_a_real_run_without_a_tag_stops(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DIST", str(_dist(tmp_path)))
    monkeypatch.setenv("TAG", "")
    monkeypatch.setenv("DRY_RUN", "false")
    assert check_dist.main() == 1
    assert "::error::No release tag" in capsys.readouterr().out


def test_a_trial_run_uploads_nothing_and_needs_no_token():
    upload = STEPS["Publish to PyPI (Trusted Publishing)"]
    trial = STEPS["Ask PyPI whether it would take the files (trial run)"]
    assert upload["if"] == "inputs.dry-run != 'true'"
    assert trial["if"] == "inputs.dry-run == 'true'"
    assert trial["run"] == 'uv publish --dry-run --trusted-publishing never "$DIST"/*'
    assert ACTION["inputs"]["dry-run"]["default"] == "false"
