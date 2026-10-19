"""The brand rules, the CI check in a git checkout, and the weekly report
against canned GitHub answers.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION_DIR = ROOT / "actions" / "brand" / "assets"
ACTION = yaml.safe_load((ACTION_DIR / "action.yml").read_text("utf-8"))
BRAND = yaml.safe_load(
    (ROOT / ".github" / "workflows" / "brand.yml").read_text("utf-8")
)

_spec = importlib.util.spec_from_file_location(
    "brand_assets", ACTION_DIR / "brand_assets.py"
)
assert _spec and _spec.loader
brand_assets = importlib.util.module_from_spec(_spec)
sys.modules["brand_assets"] = brand_assets
_spec.loader.exec_module(brand_assets)

SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg"/>\n'


def png(width: int, height: int, tail: bytes = b"") -> bytes:
    return (
        brand_assets.PNG_SIGNATURE
        + b"\x00\x00\x00\x0dIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + tail
    )


GOOD = {
    "assets/brand/icon.svg": SVG_BYTES,
    "assets/brand/icon.png": png(512, 512),
    "assets/brand/social-preview.png": png(1280, 640),
}


def _problems(files: dict[str, bytes], stale: tuple[str, ...] = ()) -> list[str]:
    found = brand_assets.problems(
        lambda p: files.get(p) or None, lambda p: p not in stale
    )
    return [f"{p.path} {p.text}" for p in found]


# The rules.


def test_good_assets_meet_the_rules():
    assert _problems(GOOD) == []


def test_every_missing_file_is_named():
    assert _problems({}) == [
        "assets/brand/icon.svg is missing",
        "assets/brand/icon.png is missing",
        "assets/brand/social-preview.png is missing",
    ]


def test_an_empty_file_counts_as_missing():
    assert _problems(GOOD | {"assets/brand/icon.svg": b""}) == [
        "assets/brand/icon.svg is missing"
    ]


def test_a_file_of_the_wrong_kind_is_named():
    files = GOOD | {
        "assets/brand/icon.svg": b"<html/>",
        "assets/brand/icon.png": b"GIF89a",
    }
    assert _problems(files) == [
        "assets/brand/icon.svg is not an SVG file",
        "assets/brand/icon.png is not a PNG file",
    ]


def test_each_png_has_its_own_size():
    files = GOOD | {
        "assets/brand/icon.png": png(256, 256),
        "assets/brand/social-preview.png": png(640, 320),
    }
    assert _problems(files) == [
        "assets/brand/icon.png is 256x256 pixels instead of 512x512",
        "assets/brand/social-preview.png is 640x320 pixels instead of 1280x640",
    ]


def test_a_png_older_than_the_svg_is_named():
    assert _problems(GOOD, stale=("assets/brand/social-preview.png",)) == [
        "assets/brand/social-preview.png is older than the last change to "
        "assets/brand/icon.svg"
    ]


# The CI check in a checkout.

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _commit(repo: Path, files: dict[str, bytes], message: str) -> None:
    for name, data in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes(data)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)


def _check(repo: Path, monkeypatch, capsys) -> tuple[int, str]:
    monkeypatch.chdir(repo)
    code = brand_assets.main(["check"])
    return code, capsys.readouterr().out


@needs_git
def test_the_check_follows_the_order_of_the_commits(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for key, value in (
        ("user.name", "t"),
        ("user.email", "t@t"),
        ("core.autocrlf", "false"),
    ):
        subprocess.run(["git", "config", key, value], cwd=tmp_path, check=True)
    _commit(tmp_path, GOOD, "all three")
    assert _check(tmp_path, monkeypatch, capsys) == (
        0,
        "All brand assets are present and current.\n",
    )

    _commit(tmp_path, {"assets/brand/icon.svg": SVG_BYTES + b"<!-- -->\n"}, "svg")
    code, out = _check(tmp_path, monkeypatch, capsys)
    assert code == 1
    assert (
        "::error file=assets/brand/icon.png::assets/brand/icon.png is older than the "
        "last change to assets/brand/icon.svg." in out
    )
    assert "assets/brand/social-preview.png is older" in out

    _commit(
        tmp_path,
        {
            "assets/brand/icon.png": png(512, 512, b"x"),
            "assets/brand/social-preview.png": png(1280, 640, b"x"),
        },
        "both PNGs exported again",
    )
    assert _check(tmp_path, monkeypatch, capsys)[0] == 0


# The report.


class FakeGitHub:
    """Two repositories, an archive, a fork and .github, with canned files."""

    def __init__(
        self, files: dict[str, dict[str, bytes]], uploaded: dict[str, bytes | None]
    ):
        self.files = files
        self.uploaded = uploaded

    def json(self, url: str) -> Any:
        if "/orgs/" in url:
            if not url.endswith("page=1"):
                return []
            return [
                {"name": n, "archived": n == "old", "fork": n == "copy"}
                for n in [*self.files, "old", "copy", ".github"]
            ]
        if "/commits?" in url:
            return [{"sha": url.split("path=")[1].split("&")[0]}]
        if "/compare/" in url:
            return {"status": "ahead"}
        raise AssertionError(url)

    def get(self, url: str, accept: str = "") -> bytes:
        if url.startswith("https://og.invalid/"):
            return self.uploaded[url.rsplit("/", 1)[1]] or b""
        repo, path = url.split("/repos/benethos-hub/")[1].split("/contents/")
        if path not in self.files[repo]:
            raise urllib.error.HTTPError(url, 404, "Not Found", Message(), None)
        return self.files[repo][path]

    def graphql(self, query: str, variables: dict[str, str]) -> Any:
        name = variables["name"]
        custom = self.uploaded.get(name) is not None
        return {
            "repository": {
                "usesCustomOpenGraphImage": custom,
                "openGraphImageUrl": f"https://og.invalid/{name}",
            }
        }


def test_the_report_lists_only_repositories_that_break_a_rule():
    github = FakeGitHub(
        {"good": GOOD, "bad": {"assets/brand/icon.svg": SVG_BYTES}},
        {"good": GOOD["assets/brand/social-preview.png"]},
    )
    body = brand_assets.report(github, "benethos-hub")
    assert body.startswith("These repositories do not meet the brand rules:\n\n")
    assert "- [bad](https://github.com/benethos-hub/bad)\n" in body
    assert "  - `assets/brand/icon.png` is missing\n" in body
    assert "[good]" not in body and "[old]" not in body and "[copy]" not in body


def test_a_missing_or_different_upload_is_reported():
    github = FakeGitHub({"none": GOOD, "other": GOOD}, {"none": None, "other": b"x"})
    body = brand_assets.report(github, "benethos-hub")
    assert (
        "- [none](https://github.com/benethos-hub/none)\n  - no social preview" in body
    )
    assert (
        "- [other](https://github.com/benethos-hub/other)\n  - the social preview "
        in body
    )


def test_a_report_without_problems_is_empty():
    github = FakeGitHub(
        {"good": GOOD}, {"good": GOOD["assets/brand/social-preview.png"]}
    )
    assert brand_assets.report(github, "benethos-hub") == ""


# The wiring.


def test_the_check_keeps_its_name_and_its_checkout():
    """The projects require the check brand / Brand assets on main."""
    job = BRAND["jobs"]["assets"]
    assert job["name"] == "Brand assets"
    checkout, action = job["steps"]
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["sparse-checkout"] == "assets/brand"
    assert action["uses"] == "benethos-hub/.github/actions/brand/assets@main"


def test_the_action_runs_the_shared_rules():
    uv, step = ACTION["runs"]["steps"]
    assert uv["uses"].startswith("astral-sh/setup-uv@")
    assert step["run"].endswith(' "$GITHUB_ACTION_PATH/brand_assets.py" check')


REPORT = yaml.safe_load(
    (ROOT / ".github" / "workflows" / "brand-report.yml").read_text("utf-8")
)


def test_the_report_applies_the_same_script():
    steps = {s.get("name"): s for s in REPORT["jobs"]["report"]["steps"]}
    assert steps["Check every repository"]["run"].endswith(
        ' actions/brand/assets/brand_assets.py report > "$RUNNER_TEMP/report.md"'
    )
    assert REPORT["jobs"]["report"]["env"]["TITLE"] == "Brand assets need fixing"


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
        ("These repositories", "", "gh issue create --title Brand assets need fixing"),
        ("These repositories", "2", "gh issue edit 2 --body These repositories"),
        ("", "2", "gh issue close 2 --comment All repositories meet the brand rules"),
        ("", "", ""),
    ],
)
def test_the_issue_follows_the_report(tmp_path, report, open_issue, expected):
    steps = {s.get("name"): s for s in REPORT["jobs"]["report"]["steps"]}
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    (tmp_path / "report.md").write_text(report, "utf-8")
    log = tmp_path / "gh.log"
    log.touch()
    script = tmp_path / "step.sh"
    script.write_text(steps["Update the issue"]["run"])
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "RUNNER_TEMP": str(tmp_path),
        "TITLE": REPORT["jobs"]["report"]["env"]["TITLE"],
        "OPEN_ISSUE": open_issue,
        "GH_LOG": str(log),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "benethos-hub/.github",
    }
    done = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert log.read_text().startswith(expected)
