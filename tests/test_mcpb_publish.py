"""The Claude Desktop bundle action: the check of the packed file, the lock of
the packer, and how the action wires them.
"""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION_DIR = ROOT / "actions" / "publish" / "mcpb"
ACTION = yaml.safe_load((ACTION_DIR / "action.yml").read_text("utf-8"))
STEPS = {step.get("name"): step for step in ACTION["runs"]["steps"]}

_spec = importlib.util.spec_from_file_location("check_packed", ACTION_DIR / "check_packed.py")
assert _spec and _spec.loader
check_packed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_packed)

TREE = {"manifest.json": b'{"version": "1.2.3"}', "src/server.py": b"print('hi')\n"}


def _staged(tmp_path: Path, files: dict[str, bytes] = TREE) -> Path:
    root = tmp_path / "bundle"
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    return root


def _packed(tmp_path: Path, files: dict[str, bytes] = TREE) -> Path:
    bundle = tmp_path / "example-1.2.3.mcpb"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("src/", "")
        for name, data in files.items():
            archive.writestr(name, data)
    return bundle


def test_a_bundle_that_is_the_staged_tree_passes(tmp_path, capsys):
    assert check_packed.main([str(_staged(tmp_path)), str(_packed(tmp_path))]) == 0
    assert "example-1.2.3.mcpb: 2 files, each as staged" in capsys.readouterr().out


def test_every_difference_is_named(tmp_path, capsys):
    packed = {"manifest.json": TREE["manifest.json"], "src/server.py": b"changed", "extra.txt": b""}
    staged = TREE | {"README.md": b"readme"}
    assert check_packed.main([str(_staged(tmp_path, staged)), str(_packed(tmp_path, packed))]) == 1
    out = capsys.readouterr().out
    assert "::error::added by the packer: extra.txt" in out
    assert "::error::missing from the bundle: README.md" in out
    assert "::error::changed by the packer: src/server.py" in out
    assert "nothing uploaded" in out


def test_a_wrong_call_prints_the_usage(capsys):
    assert check_packed.main([]) == 2
    assert "check_packed.py <staging dir> <bundle.mcpb>" in capsys.readouterr().err


def test_the_packer_is_locked_with_everything_beneath_it():
    package = json.loads((ACTION_DIR / "package.json").read_text("utf-8"))
    lock = json.loads((ACTION_DIR / "package-lock.json").read_text("utf-8"))
    wanted = package["dependencies"]["@anthropic-ai/mcpb"]
    assert wanted[0].isdigit(), "pin an exact version, Dependabot raises it"
    assert lock["packages"]["node_modules/@anthropic-ai/mcpb"]["version"] == wanted
    assert all(
        "integrity" in entry for name, entry in lock["packages"].items() if name
    ), "every package in the lock carries its hash"


def test_the_bundle_version_is_checked_first_and_against_the_manifest():
    first = ACTION["runs"]["steps"][0]
    assert first["uses"] == "benethos-hub/.github/actions/release/tag-matches-version@main"
    assert first["with"]["file"] == "${{ inputs.staged }}/manifest.json"


def test_the_packer_comes_from_the_lock_and_nothing_is_uploaded_unchecked():
    install = STEPS["Install the packer (locked)"]["run"]
    assert "npm ci" in install and "--ignore-scripts" in install
    assert '"$GITHUB_ACTION_PATH/package-lock.json"' in install
    names = [step.get("name") for step in ACTION["runs"]["steps"]]
    assert names.index("The bundle is the staged tree") < names.index("Attach it to the release")


def test_the_bundle_is_attached_with_and_without_its_version():
    pack = STEPS["Validate and pack"]["run"]
    attach = STEPS["Attach it to the release"]["run"]
    assert 'bundle="$OUT/$NAME-${TAG#v}.mcpb"' in pack
    assert 'latest="$(dirname "$BUNDLE")/$NAME.mcpb"' in attach
    assert 'gh release upload "$TAG" "$BUNDLE" "$latest"' in attach
