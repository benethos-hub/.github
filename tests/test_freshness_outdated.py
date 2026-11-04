"""The uv adapter of the freshness workflow: which packages of a lockfile are
runtime, development or direct, which are the repository's own, and what the
two uv commands say about them.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "actions" / "python" / "freshness-outdated"
ACTION = yaml.safe_load((FOLDER / "action.yml").read_text("utf-8"))

_spec = importlib.util.spec_from_file_location(
    "freshness_outdated", FOLDER / "outdated.py"
)
assert _spec and _spec.loader
outdated = importlib.util.module_from_spec(_spec)
sys.modules["freshness_outdated"] = outdated
_spec.loader.exec_module(outdated)


def _package(name: str, version: str, body: str = "") -> str:
    return f'[[package]]\nname = "{name}"\nversion = "{version}"\n{body}\n'


# A single project: mcp and pyjwt[crypto] at runtime, pytest and mcp[cli] in
# the dev extra. cryptography hangs on the extra only, numpy has two forks.
PROJECT = "\n".join(
    [
        _package(
            "example",
            "1.0.0",
            'source = { editable = "." }\n'
            "dependencies = [\n"
            '    { name = "mcp" },\n'
            '    { name = "pyjwt", extra = ["crypto"] },\n'
            '    { name = "numpy", version = "2.4.6", marker = "a" },\n'
            '    { name = "numpy", version = "2.5.4", marker = "b" },\n'
            "]\n"
            "[package.optional-dependencies]\n"
            'dev = [{ name = "pytest" }, { name = "mcp", extra = ["cli"] }]\n',
        ),
        _package(
            "mcp",
            "2.3.0",
            'dependencies = [{ name = "anyio" }]\n'
            '[package.optional-dependencies]\ncli = [{ name = "typer" }]\n',
        ),
        _package("anyio", "4.16.0"),
        _package("typer", "0.27.3"),
        _package(
            "pyjwt",
            "2.15.1",
            '[package.optional-dependencies]\ncrypto = [{ name = "cryptography" }]\n',
        ),
        _package("cryptography", "50.0.2", 'dependencies = [{ name = "cffi" }]\n'),
        _package("cffi", "2.0.0"),
        _package(
            "numpy",
            "2.4.6",
            "resolution-markers = [\"python_full_version < '3.12'\"]\n",
        ),
        _package(
            "numpy",
            "2.5.4",
            "resolution-markers = [\"python_full_version >= '3.12'\"]\n",
        ),
        _package("pytest", "9.2.0", 'dependencies = [{ name = "pluggy" }]\n'),
        _package("pluggy", "1.7.0"),
        _package("certifi", "2026.4.26"),
    ]
)

# A workspace: two members, the service needs the common package with an
# extra, the root has no package of its own and a dev group.
WORKSPACE = "\n".join(
    [
        "[manifest]",
        'members = ["example-common", "example-service"]',
        "",
        "[manifest.dependency-groups]",
        "dev = [",
        '    { name = "example-service", editable = "packages/service" },',
        '    { name = "ruff", specifier = ">=0.17" },',
        "]",
        "",
        _package(
            "example-common",
            "0.6.0",
            'source = { editable = "packages/common" }\n'
            'dependencies = [{ name = "pydantic" }]\n'
            "[package.optional-dependencies]\n"
            'settings = [{ name = "keyring" }]\n',
        ),
        _package(
            "example-service",
            "0.6.0",
            'source = { editable = "packages/service" }\n'
            "dependencies = [\n"
            '    { name = "example-common", extra = ["settings"] },\n'
            '    { name = "fastapi" },\n'
            "]\n",
        ),
        _package("pydantic", "2.14.2"),
        _package("keyring", "25.7.0"),
        _package("fastapi", "0.162.0"),
        _package("ruff", "0.17.3"),
    ]
)

# A root without a package, as the lockfile of a repository of tools.
VIRTUAL = "\n".join(
    [
        _package(
            "tools",
            "0",
            'source = { virtual = "." }\n'
            "[package.dev-dependencies]\n"
            'dev = [{ name = "mypy" }]\n',
        ),
        _package("mypy", "2.4.1"),
    ]
)

LOCK = outdated.load_lock(PROJECT)


def _scopes(lock, upgrade: dict | None = None, latest: dict | None = None):
    upgrade = upgrade or {}
    latest = latest or {}
    found = outdated.package_findings(lock, upgrade, latest, "uv.lock")
    return {(f["name"], f["current"]): f for f in found}


def _everything(lock):
    """Every package moved by a patch, to look at the scopes of all of them."""
    return _scopes(
        lock,
        upgrade={p.key: p.version + ".1" for p in lock.packages if not p.root},
    )


# --- the graph ----------------------------------------------------------------


def test_the_project_is_the_root_and_never_a_finding():
    assert [r.name for r in LOCK.roots] == ["example"]
    assert ("example", "1.0.0") not in _everything(LOCK)


def test_the_graph_is_followed_through_extras():
    found = _everything(LOCK)
    assert found[("cryptography", "50.0.2")]["scope"] == "runtime"
    assert found[("cffi", "2.0.0")]["scope"] == "runtime"


def test_a_package_in_two_versions_is_two_findings():
    found = _everything(LOCK)
    assert found[("numpy", "2.4.6")]["direct"] is True
    assert found[("numpy", "2.5.4")]["direct"] is True


def test_the_dev_extra_is_dev_and_runtime_wins():
    found = _everything(LOCK)
    assert found[("pytest", "9.2.0")]["scope"] == "dev"
    assert found[("pluggy", "1.7.0")]["scope"] == "dev"
    assert found[("mcp", "2.3.0")]["scope"] == "runtime"
    assert found[("typer", "0.27.3")]["scope"] == "dev"


def test_direct_is_what_the_project_names_in_any_scope():
    found = _everything(LOCK)
    assert found[("mcp", "2.3.0")]["direct"] is True
    assert found[("pytest", "9.2.0")]["direct"] is True
    assert found[("anyio", "4.16.0")]["direct"] is False
    assert found[("cryptography", "50.0.2")]["direct"] is False


def test_a_single_project_names_no_packages_column():
    assert "packages" not in _everything(LOCK)[("mcp", "2.3.0")]


def test_a_workspace_takes_its_members_from_the_manifest():
    lock = outdated.load_lock(WORKSPACE)
    assert [r.name for r in lock.roots] == ["example-common", "example-service"]
    found = _everything(lock)
    assert ("example-common", "0.6.0") not in found
    assert ("example-service", "0.6.0") not in found


def test_a_workspace_names_the_members_that_need_a_finding():
    found = _everything(outdated.load_lock(WORKSPACE))
    assert found[("pydantic", "2.14.2")]["packages"] == [
        "example-common",
        "example-service",
    ]
    assert found[("keyring", "25.7.0")]["packages"] == ["example-service"]
    assert found[("fastapi", "0.162.0")]["packages"] == ["example-service"]


def test_the_groups_of_a_root_without_a_package_are_dev():
    found = _everything(outdated.load_lock(WORKSPACE))
    assert found[("ruff", "0.17.3")]["scope"] == "dev"
    assert found[("ruff", "0.17.3")]["direct"] is True
    assert found[("ruff", "0.17.3")]["packages"] == []


def test_a_virtual_root_with_dependency_groups():
    lock = outdated.load_lock(VIRTUAL)
    assert [r.name for r in lock.roots] == ["tools"]
    found = _everything(lock)
    assert found[("mypy", "2.4.1")] == {
        "category": "package",
        "name": "mypy",
        "where": ["uv.lock"],
        "current": "2.4.1",
        "newest": "2.4.1.1",
        "within_bounds": True,
        "direct": True,
        "scope": "dev",
    }


# --- what uv said -------------------------------------------------------------


UPGRADE = """\
Resolved 12 packages in 160ms
Update mcp v2.3.0 -> v2.3.2
Update numpy v2.4.6 -> v2.4.7
"""

# As uv prints a package pinned in two versions, measured on a real lockfile.
FORKED_UPGRADE = """\
Update soupsieve v2.10, v4.0 -> v2.10, v4.0.1
Update numpy v2.4.6, v2.5.4 -> v2.4.7
"""

TREE = """\
example v1.0.0
├── mcp v2.3.0 (latest: v2.4.0)
│   └── anyio v4.16.0
├── numpy v2.4.6 (latest: v2.5.4)
├── numpy v2.5.4
└── pyjwt[crypto] v2.15.1 (latest: v2.16.0)
    └── cryptography v50.0.2 (extra: crypto)
"""


def test_the_dry_run_gives_the_newest_within_bounds():
    assert outdated.parse_upgrade(UPGRADE) == {
        ("mcp", "2.3.0"): "2.3.2",
        ("numpy", "2.4.6"): "2.4.7",
    }


def test_a_package_in_two_versions_is_matched_by_position():
    assert outdated.parse_upgrade(FORKED_UPGRADE) == {("soupsieve", "4.0"): "4.0.1"}


def test_the_tree_gives_the_latest_release_without_the_extras():
    assert outdated.parse_outdated(TREE) == {
        ("mcp", "2.3.0"): "2.4.0",
        ("numpy", "2.4.6"): "2.5.4",
        ("pyjwt", "2.15.1"): "2.16.0",
    }


def test_within_bounds_is_whether_the_newest_is_what_the_dry_run_reached():
    found = _scopes(
        LOCK, outdated.parse_upgrade(UPGRADE), outdated.parse_outdated(TREE)
    )
    assert found[("mcp", "2.3.0")]["newest"] == "2.4.0"
    assert found[("mcp", "2.3.0")]["within_bounds"] is False
    assert found[("pyjwt", "2.15.1")]["within_bounds"] is False
    assert found[("numpy", "2.4.6")]["newest"] == "2.5.4"
    assert ("numpy", "2.5.4") not in found
    assert ("anyio", "4.16.0") not in found


def test_a_move_the_tree_does_not_mention_is_within_bounds():
    found = _scopes(LOCK, {("mcp", "2.3.0"): "2.3.2"}, {})
    assert found[("mcp", "2.3.0")]["newest"] == "2.3.2"
    assert found[("mcp", "2.3.0")]["within_bounds"] is True


def test_a_fork_the_tree_does_not_mention_has_unknown_bounds():
    """The tree names no latest release for a package pinned twice, so the
    dry run is the only source and the bounds stay unknown."""
    found = _scopes(LOCK, {("numpy", "2.4.6"): "2.4.7"}, {})
    assert found[("numpy", "2.4.6")]["newest"] == "2.4.7"
    assert "within_bounds" not in found[("numpy", "2.4.6")]
    assert ("numpy", "2.5.4") not in found


def test_a_date_version_passes_through_unchanged():
    found = _scopes(LOCK, {}, {("certifi", "2026.4.26"): "2026.5.4"})
    assert found[("certifi", "2026.4.26")]["newest"] == "2026.5.4"
    assert "kind" not in found[("certifi", "2026.4.26")]


# --- build backends -----------------------------------------------------------


def _pyproject(folder: Path, requires: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "pyproject.toml"
    path.write_text(f"[build-system]\nrequires = [{requires}]\n", "utf-8")
    return path


def _pypi(**newest: str):
    def fetch(url: str) -> bytes:
        name = url.removeprefix(outdated.PYPI + "/").removesuffix("/json")
        return json.dumps({"info": {"version": newest[name]}}).encode()

    return fetch


def test_the_same_backend_pin_in_two_files_is_one_finding(tmp_path):
    _pyproject(tmp_path, '"hatchling==1.33.0"')
    _pyproject(tmp_path / "packages" / "a", '"hatchling==1.33.0"')
    _pyproject(tmp_path / ".venv" / "lib", '"hatchling==1.0.0"')
    pins = outdated.pinned_backends(tmp_path, outdated.pyproject_files(tmp_path))
    assert pins == {
        ("hatchling", "1.33.0"): ["packages/a/pyproject.toml", "pyproject.toml"]
    }
    (finding,) = outdated.backend_findings(pins, _pypi(hatchling="1.34.0"))
    assert finding == {
        "category": "package",
        "name": "hatchling",
        "where": ["packages/a/pyproject.toml", "pyproject.toml"],
        "current": "1.33.0",
        "newest": "1.34.0",
        "direct": True,
        "scope": "build",
    }


def test_a_folder_with_a_lockfile_of_its_own_is_left_to_its_own_run(tmp_path):
    _pyproject(tmp_path, '"hatchling==1.33.0"')
    _pyproject(tmp_path / "packages" / "a", '"hatchling==1.33.0"')
    _pyproject(tmp_path / "tools" / "audit", '"hatchling==1.0.0"')
    (tmp_path / "tools" / "audit" / "uv.lock").write_text("", "utf-8")
    pins = outdated.pinned_backends(tmp_path, outdated.pyproject_files(tmp_path))
    assert pins == {
        ("hatchling", "1.33.0"): ["packages/a/pyproject.toml", "pyproject.toml"]
    }
    own = outdated.pyproject_files(tmp_path / "tools" / "audit")
    assert [p.relative_to(tmp_path).as_posix() for p in own] == [
        "tools/audit/pyproject.toml"
    ]


def test_an_unpinned_backend_floats_and_is_left_out(tmp_path):
    _pyproject(tmp_path, '"hatchling", "setuptools>=70"')
    assert outdated.pinned_backends(tmp_path, outdated.pyproject_files(tmp_path)) == {}


def test_a_current_backend_is_no_finding(tmp_path):
    _pyproject(tmp_path, '"hatchling==1.33.0"')
    pins = outdated.pinned_backends(tmp_path, outdated.pyproject_files(tmp_path))
    assert outdated.backend_findings(pins, _pypi(hatchling="1.33.0")) == []


# --- the script ---------------------------------------------------------------


def _run(
    tmp_path: Path, lock: str = PROJECT, **env: str
) -> subprocess.CompletedProcess[str]:
    (tmp_path / "uv.lock").write_text(lock, "utf-8")
    (tmp_path / "upgrade.txt").write_text(UPGRADE, "utf-8")
    (tmp_path / "outdated.txt").write_text(TREE, "utf-8")
    _pyproject(tmp_path, '"hatchling"')
    return subprocess.run(
        [sys.executable, str(FOLDER / "outdated.py")],
        env=os.environ
        | {
            "ROOT": str(tmp_path),
            "LOCKFILE": "uv.lock",
            "UPGRADE": str(tmp_path / "upgrade.txt"),
            "OUTDATED": str(tmp_path / "outdated.txt"),
            "FINDINGS": str(tmp_path / "out"),
        }
        | env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


def test_the_script_writes_the_findings_and_the_status(tmp_path):
    run = _run(tmp_path)
    assert run.returncode == 0, run.stderr
    lines = (tmp_path / "out" / "findings.jsonl").read_text("utf-8").splitlines()
    names = sorted(json.loads(line)["name"] for line in lines)
    assert names == ["mcp", "numpy", "pyjwt"]
    status = json.loads((tmp_path / "out" / "status.json").read_text("utf-8"))
    assert status == {"result": "ok", "checked": 11, "packages": ["example"]}
    assert "11 pins checked, 3 findings." in run.stdout


def test_a_lockfile_in_a_folder_names_the_folder(tmp_path):
    folder = tmp_path / "tools" / "audit"
    folder.mkdir(parents=True)
    (folder / "uv.lock").write_text(PROJECT, "utf-8")
    run = _run(tmp_path, LOCKFILE="tools/audit/uv.lock")
    assert run.returncode == 0, run.stderr
    lines = (tmp_path / "out" / "findings.jsonl").read_text("utf-8").splitlines()
    assert {json.loads(line)["where"][0] for line in lines} == {"tools/audit/uv.lock"}


def test_a_lockfile_without_a_root_is_an_error(tmp_path):
    run = _run(tmp_path, lock=_package("mcp", "2.3.0"))
    assert run.returncode == 1
    assert "names no project and no workspace members" in run.stdout


def test_a_missing_file_is_an_error(tmp_path):
    run = _run(tmp_path, UPGRADE=str(tmp_path / "nowhere.txt"))
    assert run.returncode == 1
    assert "::error::Could not read what is pinned" in run.stderr


# --- the action ---------------------------------------------------------------


def test_the_action_runs_the_dry_run_and_the_universal_tree():
    assert set(ACTION["inputs"]) == {"findings", "directory"}
    assert ACTION["inputs"]["directory"]["default"] == "."
    runs = [s["run"] for s in ACTION["runs"]["steps"] if "run" in s]
    uv, script = runs
    assert 'uv lock --upgrade --dry-run --directory "$DIRECTORY" > /dev/null 2>' in uv
    assert 'uv tree --frozen --outdated --universal --directory "$DIRECTORY" >' in uv
    assert "Missing uv.lock" in uv
    assert '"$GITHUB_ACTION_PATH/outdated.py"' in script
    (step,) = [s for s in ACTION["runs"]["steps"] if "outdated.py" in s.get("run", "")]
    assert set(step["env"]) == {"LOCKFILE", "UPGRADE", "OUTDATED", "FINDINGS"}
    assert step["env"]["LOCKFILE"] == "${{ inputs.directory }}/uv.lock"
