"""What a user gets today: the package installed from the index, as the job
``index`` of freshness.yml leaves it for the report.

The auto-update bundles and ``uvx`` install the published wheel from the
index with its own metadata, not the checkout. A bound that is not released
yet, a build that fails or an installation that does not resolve is invisible
to a run on the checkout. The action installs the package into a fresh
virtual environment, lists what resolved, runs a check with the interpreter
of that environment, and this turns the outcomes into the artifact
``actions/freshness/report/FORMAT.md`` describes:

    status.json   ``issue: alarm``. ``ok`` with a summary when the check
                  passed, ``ok`` with a section when the installation or the
                  check failed, ``inconclusive`` when the check hit a rate
                  limit. A failed installation is a finding, not a gap: that
                  is what the job is for, and an outage of the index closes
                  itself on the next day.
    section.md    only on a failure: the installed version, the step that
                  failed and the packages that resolved.

``index.py name`` prints the name of the project in pyproject.toml, for a
caller that names no package. ``index.py write`` reads PACKAGE, INSTALL_EXIT,
FREEZE and SHOW (the output of uv pip freeze and uv pip show), CHECK and
CHECK_EXIT (empty when no check ran), RATE_LIMIT_EXIT and FINDINGS. Only names,
versions and the result of a step go in, the issues are public. Standard
library only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def project_name(pyproject: Path) -> str:
    """The name in ``[project]``, or ValueError for a file without one."""
    if not pyproject.is_file():
        raise ValueError(f"{pyproject} does not exist, name the package to install.")
    data = tomllib.loads(pyproject.read_text("utf-8"))
    name = data.get("project", {}).get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(
            f"{pyproject} has no [project] name, a workspace root has none. "
            "Name the package to install."
        )
    return name


def parse_freeze(text: str) -> dict[str, str]:
    """``name -> version`` from ``uv pip freeze``."""
    versions = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)$", line.strip())
        if match:
            versions[normalized(match[1])] = match[2]
    return versions


@dataclass(frozen=True)
class Shown:
    version: str = ""
    requires: tuple[str, ...] = field(default_factory=tuple)


def parse_show(text: str) -> Shown:
    """The version and the direct requirements from ``uv pip show``."""
    version = ""
    requires: tuple[str, ...] = ()
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "version":
            version = value.strip()
        elif key.strip().lower() == "requires":
            requires = tuple(
                normalized(r.strip()) for r in value.split(",") if r.strip()
            )
    return Shown(version, requires)


@dataclass(frozen=True)
class Outcome:
    result: str
    summary: str
    section: str
    checked: int


def _with(versions: dict[str, str], names: tuple[str, ...]) -> str:
    parts = [f"{name} {versions[name]}" for name in sorted(names) if name in versions]
    return ", ".join(parts)


def _resolved_table(package: str, versions: dict[str, str]) -> list[str]:
    lines = ["| Package | Version |", "|---|---|"]
    lines += [
        f"| `{name}` | {version} |"
        for name, version in sorted(versions.items())
        if name != normalized(package)
    ]
    return lines


def outcome(
    package: str,
    install_exit: int,
    versions: dict[str, str],
    shown: Shown,
    check: str,
    check_exit: int | None,
    rate_limit_exit: int,
) -> Outcome:
    """The status and the prose of the job from what the action measured."""
    if install_exit != 0:
        section = (
            f"`{package}` could not be installed from the index, the installation "
            f"ended with exit code {install_exit}. What a user installs today does "
            "not resolve or does not build."
        )
        return Outcome("ok", "", section + "\n", 0)
    version = shown.version or versions.get(normalized(package), "")
    installed = f"`{package}` {version} from the index".strip()
    runs_with = _with(versions, shown.requires)
    if check_exit is None:
        summary = f"{version} from the index installs with {runs_with}"
        return Outcome("ok", summary, "", len(versions))
    if check_exit == 0:
        summary = f"{version} from the index passes its check with {runs_with}"
        return Outcome("ok", summary, "", len(versions))
    if check_exit == rate_limit_exit:
        summary = (
            f"the check of {version} from the index hit a rate limit, "
            f"exit code {check_exit}"
        )
        return Outcome("inconclusive", summary, "", len(versions))
    lines = [
        f"{installed} fails its check, the installation itself worked. A user "
        "who installs it today gets these versions:",
        "",
        f"- Check: `{check}`, exit code {check_exit}",
        "",
        *_resolved_table(package, versions),
    ]
    return Outcome("ok", "", "\n".join(lines) + "\n", len(versions))


def write(folder: Path, found: Outcome) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    status: dict[str, object] = {
        "result": found.result,
        "checked": found.checked,
        "issue": "alarm",
    }
    if found.summary:
        status["summary"] = found.summary
    (folder / "status.json").write_text(json.dumps(status) + "\n", "utf-8")
    if found.section:
        (folder / "section.md").write_text(found.section, "utf-8")


def _read(variable: str) -> str:
    path = os.environ.get(variable, "")
    return Path(path).read_text("utf-8") if path and Path(path).is_file() else ""


def main(argv: list[str]) -> int:
    if argv[:1] == ["name"]:
        root = Path(os.environ.get("ROOT") or Path.cwd())
        try:
            print(project_name(root / "pyproject.toml"))
        except (OSError, ValueError) as error:
            print(f"::error::{error}", file=sys.stderr)
            return 1
        return 0
    if argv[:1] != ["write"]:
        print("usage: index.py name | index.py write", file=sys.stderr)
        return 2
    check_exit = os.environ.get("CHECK_EXIT", "")
    found = outcome(
        package=os.environ["PACKAGE"],
        install_exit=int(os.environ.get("INSTALL_EXIT", "0")),
        versions=parse_freeze(_read("FREEZE")),
        shown=parse_show(_read("SHOW")),
        check=os.environ.get("CHECK", ""),
        check_exit=int(check_exit) if check_exit else None,
        rate_limit_exit=int(os.environ.get("RATE_LIMIT_EXIT", "3")),
    )
    write(Path(os.environ["FINDINGS"]), found)
    print(f"index: {found.result}, {found.summary or 'see section.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
