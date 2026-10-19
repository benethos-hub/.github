"""Dependabot sees every pinned action and every lockfile in this repository.

The repositories of the organisation call these workflows and actions at
main, so their own Dependabot never sees the pins in here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text("utf-8"))


def _watched(ecosystem: str) -> set[str]:
    (entry,) = [u for u in CONFIG["updates"] if u["package-ecosystem"] == ecosystem]
    return set(entry["directories"])


def _folder(path: Path) -> str:
    folder = path.parent.relative_to(ROOT).as_posix()
    return "/" if folder == "." else "/" + folder


def test_every_action_that_uses_another_is_watched():
    watched = _watched("github-actions")
    needed = {
        _folder(path)
        for path in (ROOT / "actions").rglob("action.yml")
        if any("uses" in step for step in yaml.safe_load(path.read_text("utf-8"))["runs"]["steps"])
    }
    assert "/" in watched
    assert needed <= watched, f"add to dependabot.yml: {sorted(needed - watched)}"


@pytest.mark.parametrize(("ecosystem", "lockfile"), [("uv", "uv.lock"), ("npm", "package-lock.json")])
def test_every_lockfile_is_watched(ecosystem, lockfile):
    watched = _watched(ecosystem)
    needed = {
        _folder(path)
        for path in ROOT.rglob(lockfile)
        if not {".git", ".venv", "node_modules"} & set(path.parts)
    }
    assert needed == watched, f"dependabot.yml lists {sorted(watched)}, the lockfiles are in {sorted(needed)}"
