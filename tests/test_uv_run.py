"""Every script an action or workflow runs without a project gets the same
lowest Python version, the one this repository is checked against.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FLOOR = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"][
    "requires-python"
]


def _run_steps() -> list[tuple[str, str]]:
    found = []
    files = [
        *(ROOT / "actions").rglob("action.yml"),
        *(ROOT / ".github" / "actions").rglob("action.yml"),
        *(ROOT / ".github" / "workflows").glob("*.yml"),
    ]
    for path in files:
        data = yaml.safe_load(path.read_text("utf-8"))
        if "runs" in data:
            steps = data["runs"]["steps"]
        else:
            steps = [s for job in data["jobs"].values() for s in job.get("steps", [])]
        name = path.relative_to(ROOT).as_posix()
        found += [(name, s["run"]) for s in steps if "run" in s]
    return found


def test_every_script_without_a_project_names_the_lowest_python():
    calls = [
        (name, line.strip())
        for name, run in _run_steps()
        for line in run.splitlines()
        if "uv run --no-project" in line
    ]
    assert calls
    wrong = [
        (name, line)
        for name, line in calls
        if not re.search(rf'uv run --no-project --python "{re.escape(FLOOR)}" ', line)
    ]
    assert wrong == [], f'add --python "{FLOOR}" to: {wrong}'


def _setup_uv(folder: Path, pattern: str) -> list[tuple[str, dict[str, object]]]:
    found = []
    for path in sorted(folder.glob(pattern)):
        data = yaml.safe_load(path.read_text("utf-8"))
        if "runs" in data:
            steps = data["runs"]["steps"]
        else:
            steps = [s for job in data["jobs"].values() for s in job.get("steps", [])]
        name = path.relative_to(ROOT).as_posix()
        found += [
            (name, step.get("with") or {})
            for step in steps
            if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
        ]
    return found


def test_no_action_saves_the_uv_cache():
    """The job's own setup-uv owns the cache. A second one in an action would
    race it for the same key."""
    steps = _setup_uv(ROOT / "actions", "**/action.yml")
    steps += _setup_uv(ROOT / ".github" / "actions", "**/action.yml")
    assert steps
    assert [name for name, w in steps if w.get("enable-cache") is not False] == []


def test_every_workflow_caches_under_a_key_of_its_own():
    """Jobs that run side by side with the same key race each other, and the
    loser restores a cache filled by another job."""
    keys = [
        (w.get("cache-suffix", ""), w.get("python-version", ""), name)
        for name, w in _setup_uv(ROOT / ".github" / "workflows", "*.yml")
        if w.get("enable-cache") is not False
    ]
    assert keys
    seen: dict[tuple[object, object], str] = {}
    for suffix, python, name in keys:
        assert (suffix, python) not in seen, (
            f"{name} shares its key with {seen[(suffix, python)]}"
        )
        seen[(suffix, python)] = name
