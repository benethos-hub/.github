"""Publishing to the MCP Registry: the entry script and the action's steps.

The steps run in bash with stand-ins for mcp-publisher and gh. The stand-in
publisher refuses as often as a test asks and records what it was offered,
so the retries and the fallback without the bundle run without a registry.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION_DIR = ROOT / "actions" / "publish" / "mcp-registry"
ACTION = yaml.safe_load((ACTION_DIR / "action.yml").read_text("utf-8"))
STEPS = {step.get("name"): step for step in ACTION["runs"]["steps"]}

_spec = importlib.util.spec_from_file_location("registry_entry", ACTION_DIR / "registry_entry.py")
assert _spec and _spec.loader
registry_entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(registry_entry)

BUNDLE = "benethos-example-1.2.3.mcpb"


def _entry(tmp_path: Path, with_bundle: bool = True, sha: str = "0" * 64) -> Path:
    packages: list[dict[str, Any]] = [
        {"registryType": "pypi", "identifier": "benethos-example", "version": "1.2.3"}
    ]
    if with_bundle:
        packages.append(
            {
                "registryType": "mcpb",
                "identifier": f"https://github.com/benethos-hub/example/releases/download/v1.2.3/{BUNDLE}",
                "fileSha256": sha,
            }
        )
    path = tmp_path / "server.json"
    entry = {"name": "io.github.benethos-hub/example", "version": "1.2.3", "description": "Grüße", "packages": packages}
    path.write_text(json.dumps(entry, indent=2), "utf-8")
    return path


# The entry script.


def test_the_bundle_name_comes_from_the_entry(tmp_path):
    assert registry_entry.bundle_name(_entry(tmp_path)) == BUNDLE
    assert registry_entry.bundle_name(_entry(tmp_path, with_bundle=False)) == ""


def test_the_checksum_of_the_named_bundle_is_filled_in(tmp_path):
    entry = _entry(tmp_path)
    bundle = tmp_path / BUNDLE
    bundle.write_bytes(b"the bundle")
    digest = registry_entry.fill(entry, bundle)
    assert digest == hashlib.sha256(b"the bundle").hexdigest()
    raw = entry.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"\n")
    assert "Grüße" in raw.decode("utf-8")
    (mcpb,) = [p for p in json.loads(raw)["packages"] if p["registryType"] == "mcpb"]
    assert mcpb["fileSha256"] == digest


def test_another_file_is_refused(tmp_path):
    other = tmp_path / "benethos-example-1.2.2.mcpb"
    other.write_bytes(b"old")
    with pytest.raises(SystemExit, match="is not the file the entry points at"):
        registry_entry.fill(_entry(tmp_path), other)


def test_a_hash_is_never_written_twice(tmp_path):
    bundle = tmp_path / BUNDLE
    bundle.write_bytes(b"the bundle")
    with pytest.raises(SystemExit, match="not the placeholder"):
        registry_entry.fill(_entry(tmp_path, sha="a" * 64), bundle)


def test_drop_keeps_every_other_package(tmp_path):
    entry = _entry(tmp_path)
    registry_entry.drop(entry)
    assert [p["registryType"] for p in json.loads(entry.read_text("utf-8"))["packages"]] == ["pypi"]
    with pytest.raises(SystemExit, match="no bundle to drop"):
        registry_entry.drop(entry)


def test_a_wrong_call_prints_the_usage(capsys):
    assert registry_entry.main(["fill"]) == 2
    assert "usage:" in capsys.readouterr().err


# The action.


def test_the_entry_version_is_checked_against_the_tag_first():
    first = ACTION["runs"]["steps"][0]
    assert first["uses"] == "benethos-hub/.github/actions/release/tag-matches-version@main"
    assert first["with"] == {"file": "${{ inputs.entry }}", "tag": "${{ inputs.tag }}"}


def test_mcp_publisher_is_pinned_with_its_checksum():
    env = STEPS["Install mcp-publisher"]["env"]
    assert re.fullmatch(r"v\d+\.\d+\.\d+", env["MCP_PUBLISHER_VERSION"])
    assert re.fullmatch(r"[0-9a-f]{64}", env["MCP_PUBLISHER_SHA256"])
    assert "sha256sum -c -" in STEPS["Install mcp-publisher"]["run"]


UV = shutil.which("uv")
needs_bash = pytest.mark.skipif(
    sys.platform == "win32" or UV is None, reason="the steps run in bash and call uv"
)

FAKE_PUBLISHER = r"""#!/bin/bash
[ "$1" = publish ] || exit 0
types=$(grep -o '"registryType": *"[a-z]*"' "$2" | sed 's/.*"\([a-z]*\)"$/\1/' | paste -sd' ')
echo "publish $types" >> "$PUBLISHER_LOG"
count=$(grep -c '^publish' "$PUBLISHER_LOG")
[ "$count" -gt "$REFUSE" ] && exit 0
echo "refused"
exit 1
"""

FAKE_GH = r"""#!/bin/bash
# gh release download <tag> --pattern <name> --dir <dir> --clobber
echo "gh $*" >> "$PUBLISHER_LOG"
printf 'the bundle' > "$7/$5"
"""


def _step(tmp_path: Path, name: str, env: dict[str, str]) -> tuple[int, str, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for tool, body in (("mcp-publisher", FAKE_PUBLISHER), ("gh", FAKE_GH)):
        path = bin_dir / tool
        path.write_text(body)
        path.chmod(0o755)
    log = tmp_path / "publisher.log"
    log.touch()
    script = tmp_path / "step.sh"
    script.write_text(STEPS[name]["run"])
    full_env = {
        "PATH": f"{bin_dir}:{Path(str(UV)).parent}:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", str(tmp_path)),
        "GITHUB_ACTION_PATH": str(ACTION_DIR),
        "RUNNER_TEMP": str(tmp_path),
        "PUBLISHER": str(bin_dir / "mcp-publisher"),
        "PUBLISHER_LOG": str(log),
        "WAIT_SECONDS": "0",
        **env,
    }
    done = subprocess.run(["bash", str(script)], env=full_env, capture_output=True, text=True, check=False)
    return done.returncode, done.stdout + done.stderr, log.read_text().splitlines()


@needs_bash
def test_an_entry_taken_at_once_is_published_once(tmp_path):
    entry = _entry(tmp_path)
    code, _, calls = _step(tmp_path, "Publish the entry", {"ENTRY": str(entry), "ATTEMPTS": "6", "REFUSE": "0"})
    assert code == 0 and calls == ["publish pypi mcpb"]


@needs_bash
def test_a_refusal_is_retried(tmp_path):
    entry = _entry(tmp_path)
    code, out, calls = _step(tmp_path, "Publish the entry", {"ENTRY": str(entry), "ATTEMPTS": "3", "REFUSE": "2"})
    assert code == 0 and calls == ["publish pypi mcpb"] * 3
    assert "attempt 2 refused" in out


@needs_bash
def test_a_lasting_refusal_falls_back_to_the_entry_without_the_bundle(tmp_path):
    entry = _entry(tmp_path)
    code, out, calls = _step(tmp_path, "Publish the entry", {"ENTRY": str(entry), "ATTEMPTS": "3", "REFUSE": "3"})
    assert code == 1
    assert calls == ["publish pypi mcpb"] * 3 + ["publish pypi"]
    assert "::warning::The registry refused the entry with the bundle" in out
    assert "::error::Listed without the bundle" in out


@needs_bash
def test_an_entry_without_a_bundle_has_no_fallback(tmp_path):
    entry = _entry(tmp_path, with_bundle=False)
    code, out, calls = _step(tmp_path, "Publish the entry", {"ENTRY": str(entry), "ATTEMPTS": "2", "REFUSE": "9"})
    assert code == 1 and calls == ["publish pypi"] * 2
    assert "refused the entry 2 times" in out


@needs_bash
def test_the_checksum_is_taken_from_the_release_asset(tmp_path):
    entry = _entry(tmp_path)
    code, _, calls = _step(tmp_path, "Fill in the bundle's checksum", {"ENTRY": str(entry), "TAG": "v1.2.3", "REFUSE": "0"})
    assert code == 0
    assert calls == [f"gh release download v1.2.3 --pattern {BUNDLE} --dir {tmp_path} --clobber"]
    (mcpb,) = [p for p in json.loads(entry.read_text("utf-8"))["packages"] if p["registryType"] == "mcpb"]
    assert mcpb["fileSha256"] == hashlib.sha256(b"the bundle").hexdigest()


@needs_bash
def test_without_a_bundle_nothing_is_downloaded(tmp_path):
    entry = _entry(tmp_path, with_bundle=False)
    code, out, calls = _step(tmp_path, "Fill in the bundle's checksum", {"ENTRY": str(entry), "TAG": "v1.2.3", "REFUSE": "0"})
    assert code == 0 and calls == []
    assert "nothing to fill in" in out
