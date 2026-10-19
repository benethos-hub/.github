"""Dependabot sees every pinned action in this repository.

The repositories of the organisation call these workflows and actions at
main, so their own Dependabot never sees the pins in here.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text("utf-8"))


def test_every_action_that_uses_another_is_watched():
    (actions,) = [u for u in CONFIG["updates"] if u["package-ecosystem"] == "github-actions"]
    watched = set(actions["directories"])
    needed = {
        "/" + path.parent.relative_to(ROOT).as_posix()
        for path in (ROOT / "actions").rglob("action.yml")
        if any("uses" in step for step in yaml.safe_load(path.read_text("utf-8"))["runs"]["steps"])
    }
    assert "/" in watched
    assert needed <= watched, f"add to dependabot.yml: {sorted(needed - watched)}"
