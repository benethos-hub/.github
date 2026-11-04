"""The newest versions a repository's bounds allow, tested, as the job
``newest`` leaves it for the freshness report.

``uv lock --upgrade`` moves every package as far as pyproject.toml allows,
which is what an installation without the lockfile gets. The action runs the
tests and an optional check of the repository on those versions, after the
same check on the locked ones, and this turns the outcomes into the artifact
``actions/freshness/report/FORMAT.md`` describes:

    status.json   ``issue: alarm``. ``ok`` when the run says something about
                  the versions, with a summary of what passed and what moved.
                  ``inconclusive`` when it does not: the locked versions
                  failed the check too, the check hit a rate limit, or
                  nothing moved and a step still failed, which is then the
                  code or the counterpart and not a version.
    section.md    only when the newest versions fail: which step, and what
                  moved against uv.lock, so one of those is the likely cause.

BEFORE and AFTER name the lockfile as committed and after the upgrade,
LOCKED, TESTS and CHECK the outcomes (success, failure, rate-limited or
skipped), TESTS_COMMAND and CHECK_COMMAND the commands for the prose,
FINDINGS the folder to write. The graph of the lockfile is read with the
loader of the outdated adapter next to this action, the kind of a move with
the rule of the report. Standard library only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ACTIONS = Path(__file__).resolve().parent.parent.parent


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


outdated: Any = _load(
    "freshness_outdated", ACTIONS / "python" / "freshness-outdated" / "outdated.py"
)
report: Any = _load("freshness_report", ACTIONS / "freshness" / "report" / "report.py")


def runtime_versions(lock: Any) -> dict[str, list[str]]:
    """``name -> versions`` of every package a user of the repository gets,
    the repository's own packages left out."""
    roots = {r.name for r in lock.roots}
    versions: dict[str, list[str]] = {}
    for name, version in sorted(
        outdated.reach(lock, outdated._runtime_starts(lock.roots))
    ):
        if name not in roots and version:
            versions.setdefault(name, []).append(version)
    return versions


def moved(before: Any, after: Any) -> list[tuple[str, str, str]]:
    """Every runtime package the upgrade moved: name, versions before and
    after, each joined when a package is pinned in several versions."""
    old, new = runtime_versions(before), runtime_versions(after)
    return [
        (name, ", ".join(old.get(name, [])) or "-", ", ".join(new[name]))
        for name in sorted(new)
        if old.get(name) != new[name]
    ]


def verdict(
    changes: list[tuple[str, str, str]], locked: str, tests: str, check: str
) -> str:
    if locked in ("failure", "rate-limited") or check == "rate-limited":
        return "inconclusive"
    failed = tests == "failure" or check == "failure"
    if failed and not changes:
        return "inconclusive"
    return "ok"


def reason(
    changes: list[tuple[str, str, str]], locked: str, tests: str, check: str
) -> str:
    """Why the run proved nothing, for an inconclusive status."""
    if locked == "failure":
        return "the check failed on the locked versions as well"
    if locked == "rate-limited":
        return "the check hit a rate limit on the locked versions"
    if check == "rate-limited":
        return "the check hit a rate limit on the newest versions allowed"
    what = "the tests" if tests == "failure" else "the check"
    return f"{what} failed although nothing moved against uv.lock"


def summary(changes: list[tuple[str, str, str]], check: str) -> str:
    passed = "the tests" + (" and the check" if check != "skipped" else "")
    if not changes:
        return f"{passed} passed, uv.lock already holds the newest versions allowed"
    versions = ", ".join(f"{name} {new}" for name, _, new in changes)
    return f"{passed} passed on the newest versions allowed ({versions})"


def section(
    changes: list[tuple[str, str, str]],
    tests: str,
    check: str,
    tests_command: str,
    check_command: str,
) -> str:
    """The alarm's prose when a step failed on versions that differ from the
    lockfile, empty otherwise."""
    if not changes or (tests != "failure" and check != "failure"):
        return ""
    lines = [
        "The newest versions pyproject.toml allows fail, while the versions in "
        "`uv.lock` pass. An installation without the lockfile gets these "
        "versions, so its users may be affected.",
        "",
        f"- Tests: {tests}, `{tests_command}`",
    ]
    if check != "skipped":
        lines.append(f"- Check: {check}, `{check_command}`")
    lines += [
        "",
        "| Package | In `uv.lock` | Newest allowed | Kind |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| `{name}` | {old} | {new} | {report.kind(old, new)} |"
        for name, old, new in changes
    ]
    return "\n".join(lines) + "\n"


def write(
    folder: Path, result: str, text: str, checked: int, summary_text: str
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    status = {
        "result": result,
        "checked": checked,
        "issue": "alarm",
        "summary": summary_text,
    }
    (folder / "status.json").write_text(json.dumps(status) + "\n", "utf-8")
    if text:
        (folder / "section.md").write_text(text, "utf-8")


def main() -> int:
    try:
        before = outdated.load_lock(Path(os.environ["BEFORE"]).read_text("utf-8"))
        after = outdated.load_lock(Path(os.environ["AFTER"]).read_text("utf-8"))
    except (OSError, ValueError, KeyError) as error:
        print(f"::error::Could not read the lockfiles: {error}", file=sys.stderr)
        return 1
    locked = os.environ.get("LOCKED", "skipped")
    tests = os.environ.get("TESTS", "failure")
    check = os.environ.get("CHECK", "skipped")
    changes = moved(before, after)
    result = verdict(changes, locked, tests, check)
    if result == "ok":
        text = section(
            changes,
            tests,
            check,
            os.environ.get("TESTS_COMMAND", ""),
            os.environ.get("CHECK_COMMAND", ""),
        )
        said = "" if text else summary(changes, check)
    else:
        text = ""
        said = reason(changes, locked, tests, check)
    write(
        Path(os.environ["FINDINGS"]), result, text, len(runtime_versions(after)), said
    )
    print(f"newest: {result}, {len(changes)} runtime packages moved. {said}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
