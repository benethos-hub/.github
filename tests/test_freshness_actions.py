"""The action check of the freshness workflow, against a stand-in GitHub API:
which uses: lines are pins, and how a release's tag becomes a commit.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "actions" / "freshness" / "actions"
ACTION = yaml.safe_load((FOLDER / "action.yml").read_text("utf-8"))

_spec = importlib.util.spec_from_file_location(
    "freshness_actions", FOLDER / "actions.py"
)
assert _spec and _spec.loader
actions = importlib.util.module_from_spec(_spec)
sys.modules["freshness_actions"] = actions
_spec.loader.exec_module(actions)

CHECKOUT = "3d3c42e5aac5ba805825da76410c181273ba90b1"
OLDER = "a" * 40
TAG_OBJECT = "b" * 40
NEWER = "c" * 40

WORKFLOW = f"""\
jobs:
  lint:
    uses: example/.github/.github/workflows/lint.yml@main
  build:
    steps:
      - uses: actions/checkout@{CHECKOUT} # v7.0.1
      - uses: "actions/cache/restore@{OLDER}" # v4.2.0
      - uses: example/tool@{OLDER}
      - uses: ./actions/local
      - uses: docker://alpine:3.20
      - uses: astral-sh/setup-uv@v7
      - name: Not a pin
        run: echo "uses: nothing@{NEWER}"
"""


def _api(releases: dict[str, str], refs: dict[str, tuple[str, str]], tags=None):
    """Releases as repository -> tag, refs as repository/tag -> (type, sha),
    tags as repository -> list of names."""
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, bytes]:
        calls.append(url)
        path = url.removeprefix(actions.API + "/repos/")
        repository, _, rest = path.partition("/")
        repository += "/" + rest.split("/")[0]
        rest = rest.split("/", 1)[1] if "/" in rest else ""
        if rest == "releases/latest":
            if repository not in releases:
                return 404, b""
            return 200, json.dumps({"tag_name": releases[repository]}).encode()
        if rest.startswith("tags?"):
            names = (tags or {}).get(repository, [])
            return 200, json.dumps(
                [{"name": n, "commit": {"sha": "x"}} for n in names]
            ).encode()
        if rest.startswith("git/ref/tags/"):
            key = f"{repository}/{rest.removeprefix('git/ref/tags/')}"
            if key not in refs:
                return 404, b""
            kind, sha = refs[key]
            return 200, json.dumps({"object": {"type": kind, "sha": sha}}).encode()
        if rest.startswith("git/tags/"):
            return 200, json.dumps(
                {"object": {"type": "commit", "sha": NEWER}}
            ).encode()
        raise AssertionError(url)

    return actions.Api(fetch), calls


# --- the pins -----------------------------------------------------------------


def test_only_a_commit_is_a_pin_and_the_comment_is_its_version():
    assert actions.pins_in(WORKFLOW) == [
        actions.Pin("actions/checkout", CHECKOUT, "v7.0.1"),
        actions.Pin("actions/cache", OLDER, "v4.2.0"),
        actions.Pin("example/tool", OLDER, ""),
    ]


def test_the_same_commit_in_two_files_is_one_pin_with_the_version_of_either(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(f"    - uses: example/tool@{OLDER}\n", "utf-8")
    (workflows / "publish.yaml").write_text(
        f"    - uses: example/tool@{OLDER} # v1.2.0\n", "utf-8"
    )
    action = tmp_path / "actions" / "own"
    action.mkdir(parents=True)
    (action / "action.yml").write_text(
        f"    - uses: example/tool/sub@{OLDER} # v1.2.0\n", "utf-8"
    )
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "action.yml").write_text(
        f"uses: a/b@{OLDER}\n", "utf-8"
    )
    pins = actions.collect(tmp_path, actions.files_to_read(tmp_path))
    assert pins == {
        actions.Pin("example/tool", OLDER, "v1.2.0"): [
            ".github/workflows/ci.yml",
            ".github/workflows/publish.yaml",
            "actions/own/action.yml",
        ]
    }


# --- the release --------------------------------------------------------------


def test_a_pin_on_the_newest_release_is_no_finding():
    api, _ = _api(
        {"actions/checkout": "v7.0.1"},
        {"actions/checkout/v7.0.1": ("commit", CHECKOUT)},
    )
    assert (
        actions.check(actions.Pin("actions/checkout", CHECKOUT, "v7.0.1"), ["f"], api)
        is None
    )


def test_a_newer_release_is_a_finding_with_the_version_of_the_comment():
    api, _ = _api(
        {"actions/checkout": "v7.1.0"}, {"actions/checkout/v7.1.0": ("commit", NEWER)}
    )
    finding = actions.check(
        actions.Pin("actions/checkout", CHECKOUT, "v7.0.1"), ["ci.yml"], api
    )
    assert finding == {
        "category": "action",
        "name": "actions/checkout",
        "where": ["ci.yml"],
        "current": "v7.0.1",
        "newest": "v7.1.0",
    }


def test_a_pin_without_a_comment_shows_its_short_commit():
    api, _ = _api(
        {"example/tool": "v2.0.0"}, {"example/tool/v2.0.0": ("commit", NEWER)}
    )
    finding = actions.check(actions.Pin("example/tool", OLDER, ""), ["f"], api)
    assert finding and finding["current"] == OLDER[:12]


def test_an_annotated_tag_is_resolved_through_its_tag_object():
    api, calls = _api(
        {"example/tool": "v2.0.0"}, {"example/tool/v2.0.0": ("tag", TAG_OBJECT)}
    )
    assert (
        actions.check(actions.Pin("example/tool", NEWER, "v2.0.0"), ["f"], api) is None
    )
    assert calls[-1].endswith(f"/git/tags/{TAG_OBJECT}")


def test_a_repository_without_releases_takes_its_newest_version_tag():
    api, _ = _api(
        {},
        {"example/tool/v1.10.0": ("commit", NEWER)},
        {"example/tool": ["v1.9.0", "v1.10.0", "latest", "v1.2.0"]},
    )
    finding = actions.check(actions.Pin("example/tool", OLDER, "v1.9.0"), ["f"], api)
    assert finding and finding["newest"] == "v1.10.0"


def test_a_repository_without_releases_and_tags_is_a_warning(capsys):
    api, _ = _api({}, {})
    assert actions.check(actions.Pin("example/tool", OLDER, ""), ["f"], api) is None
    assert "::warning::example/tool has no release" in capsys.readouterr().out


def test_an_api_error_stops_the_check():
    api = actions.Api(lambda url: (403, b""))
    with pytest.raises(LookupError):
        actions.check(actions.Pin("example/tool", OLDER, ""), ["f"], api)


# --- the script ---------------------------------------------------------------


def test_the_script_writes_the_status_without_pins(tmp_path):
    run = subprocess.run(
        [sys.executable, str(FOLDER / "actions.py")],
        env=os.environ | {"ROOT": str(tmp_path), "FINDINGS": str(tmp_path / "out")},
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "out" / "findings.jsonl").read_text("utf-8") == ""
    status = json.loads((tmp_path / "out" / "status.json").read_text("utf-8"))
    assert status == {"result": "ok", "checked": 0}


# --- the action ---------------------------------------------------------------


def test_the_action_passes_the_token_and_the_folder():
    assert set(ACTION["inputs"]) == {"findings", "token"}
    assert ACTION["inputs"]["token"]["default"] == "${{ github.token }}"
    (run,) = [s for s in ACTION["runs"]["steps"] if "run" in s]
    assert '"$GITHUB_ACTION_PATH/actions.py"' in run["run"]
    assert set(run["env"]) == {"GH_TOKEN", "FINDINGS"}
