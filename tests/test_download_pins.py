"""The report on pinned downloads, against canned GitHub releases.

The fetch stand-in serves release JSON and checksums files by URL, so the
report runs without the network. The last tests hold the real list to the
files it names.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".github" / "download-pins.yml"
WORKFLOW = yaml.safe_load(
    (ROOT / ".github" / "workflows" / "download-pins-report.yml").read_text("utf-8")
)

_spec = importlib.util.spec_from_file_location(
    "download_pins", ROOT / ".github" / "scripts" / "download_pins.py"
)
assert _spec and _spec.loader
download_pins = importlib.util.module_from_spec(_spec)
# A dataclass looks its module up in sys.modules while it is being defined.
sys.modules["download_pins"] = download_pins
_spec.loader.exec_module(download_pins)

API = "https://api.github.com/repos/example/tool/releases"
BASE = "https://github.com/benethos-hub/.github"
SHA = {"v1.9.0": "a" * 64, "v1.10.0": "b" * 64}


def _pin(**overrides: str) -> object:
    fields = {
        "name": "tool",
        "file": "action.yml",
        "version": "TOOL_VERSION",
        "sha256": "TOOL_SHA256",
        "repository": "example/tool",
        "asset": "tool_linux_amd64.tar.gz",
        "checksums": "_checksums.txt",
    } | overrides
    return download_pins.Pin(**fields)


def _pinned(tmp_path: Path, version: str = "v1.9.0", sha: str = SHA["v1.9.0"]) -> Path:
    (tmp_path / "action.yml").write_text(
        f"env:\n  TOOL_VERSION: {version}\n  TOOL_SHA256: {sha}  # pinned\n", "utf-8"
    )
    return tmp_path


def _fetch(latest: str = "v1.9.0"):
    def release(tag: str) -> bytes:
        return json.dumps(
            {
                "tag_name": tag,
                "html_url": f"https://github.com/example/tool/releases/tag/{tag}",
                "assets": [
                    {"name": "tool_linux_amd64.tar.gz", "browser_download_url": "unused"},
                    {"name": f"tool_{tag}_checksums.txt", "browser_download_url": f"sums/{tag}"},
                ],
            }
        ).encode()

    def fetch(url: str) -> bytes:
        if url == f"{API}/latest":
            return release(latest)
        if url.startswith(f"{API}/tags/"):
            return release(url.rsplit("/", 1)[1])
        if url.startswith("sums/"):
            tag = url.split("/", 1)[1]
            return f"{'c' * 64}  other.tar.gz\n{SHA[tag]}  tool_linux_amd64.tar.gz\n".encode()
        raise AssertionError(url)

    return fetch


def test_a_current_pin_is_not_reported(tmp_path):
    assert download_pins.report([_pin()], _pinned(tmp_path), _fetch(), BASE) == ""


def test_a_newer_release_comes_with_the_lines_to_paste(tmp_path):
    body = download_pins.report([_pin()], _pinned(tmp_path), _fetch(latest="v1.10.0"), BASE)
    assert body.startswith("These pinned downloads need an update:\n\n### tool\n")
    assert f"[action.yml]({BASE}/blob/main/action.yml) pins v1.9.0." in body
    assert f"TOOL_VERSION: v1.10.0\nTOOL_SHA256: {SHA['v1.10.0']}\n" in body
    assert "[checksums file](sums/v1.10.0)" in body


def test_a_checksum_that_is_not_the_official_one_is_reported(tmp_path):
    body = download_pins.report([_pin()], _pinned(tmp_path, sha="d" * 64), _fetch(), BASE)
    assert "with a checksum that is not the one in the [checksums file](sums/v1.9.0)" in body
    assert f"TOOL_SHA256: {SHA['v1.9.0']}" in body


def test_a_file_without_the_keys_is_reported(tmp_path):
    (tmp_path / "action.yml").write_text("env: {}\n", "utf-8")
    body = download_pins.report([_pin()], tmp_path, _fetch(), BASE)
    assert "has no TOOL_VERSION or no TOOL_SHA256" in body


def test_versions_compare_by_number_not_by_text():
    assert download_pins.version_key("v1.10.0") > download_pins.version_key("v1.9.0")
    assert download_pins.version_key("v2.0.0") > download_pins.version_key("v1.99.9")


def test_a_release_without_the_asset_is_an_error(tmp_path):
    with pytest.raises(LookupError, match="lists no tool_linux_arm64.tar.gz"):
        download_pins.report(
            [_pin(asset="tool_linux_arm64.tar.gz")], _pinned(tmp_path), _fetch(), BASE
        )


def test_the_token_goes_to_the_api_only(monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"{}"

    def urlopen(request, timeout):
        seen.append((request.full_url, request.get_header("Authorization")))
        return Response()

    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setattr(download_pins.urllib.request, "urlopen", urlopen)
    download_pins.fetch_url("https://api.github.com/repos/example/tool/releases/latest")
    download_pins.fetch_url("https://github.com/example/tool/releases/download/v1/sums.txt")
    assert seen == [
        ("https://api.github.com/repos/example/tool/releases/latest", "Bearer secret"),
        ("https://github.com/example/tool/releases/download/v1/sums.txt", None),
    ]


# The real list.


def test_every_entry_names_a_file_that_pins_both_values():
    pins = download_pins.load(CONFIG)
    assert pins
    for pin in pins:
        text = (ROOT / pin.file).read_text("utf-8")
        assert download_pins.pinned_value(text, pin.version).startswith("v"), pin.name
        assert len(download_pins.pinned_value(text, pin.sha256)) == 64, pin.name


def test_the_workflow_runs_the_script_from_the_lockfile():
    steps = WORKFLOW["jobs"]["report"]["steps"]
    (check,) = [s for s in steps if s.get("name") == "Check every pin"]
    assert check["run"] == 'uv run --frozen .github/scripts/download_pins.py > "$RUNNER_TEMP/report.md"'


FAKE_GH = r"""#!/bin/bash
case "$*" in
  "issue list"*) echo "$OPEN_ISSUE" ;;
  issue*) printf 'gh %s\n' "$*" >> "$GH_LOG" ;;
esac
"""


@pytest.mark.skipif(sys.platform == "win32", reason="the step runs in bash")
@pytest.mark.parametrize(
    ("report", "open_issue", "expected"),
    [
        ("These pinned downloads need an update:", "", "gh issue create --title Pinned downloads need an update --body These pinned"),
        ("These pinned downloads need an update:", "7", "gh issue edit 7 --body These pinned"),
        ("", "7", "gh issue close 7 --comment Every pinned download is current now."),
        ("", "", ""),
    ],
)
def test_the_issue_follows_the_report(tmp_path, report, open_issue, expected):
    (step,) = [s for s in WORKFLOW["jobs"]["report"]["steps"] if s.get("name") == "Update the issue"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    (tmp_path / "report.md").write_text(report, "utf-8")
    log = tmp_path / "gh.log"
    log.touch()
    script = tmp_path / "step.sh"
    script.write_text(step["run"])
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "RUNNER_TEMP": str(tmp_path),
        "TITLE": WORKFLOW["jobs"]["report"]["env"]["TITLE"],
        "OPEN_ISSUE": open_issue,
        "GH_LOG": str(log),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "benethos-hub/.github",
    }
    done = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert log.read_text().startswith(expected)


@pytest.mark.parametrize(
    ("entry", "named"),
    [
        ("- name: tool\n  file: action.yml\n", "Missing: asset, checksums, repository, sha256, version"),
        (
            "- name: tool\n  file: action.yml\n  version: V\n  sha256: S\n  repository: r/t\n"
            "  asset: a\n  checksums: c\n  checksum: typo\n",
            "Unknown: checksum.",
        ),
        ("- just a text\n", "Missing: asset, checksums, file, name"),
    ],
)
def test_a_broken_entry_is_named_without_a_traceback(tmp_path, monkeypatch, capsys, entry, named):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "download-pins.yml").write_text(entry, "utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONFIG", raising=False)
    assert download_pins.main() == 1
    err = capsys.readouterr().err
    assert err.startswith("::error::Could not check the pinned downloads: entry 1 of ")
    assert named in err
