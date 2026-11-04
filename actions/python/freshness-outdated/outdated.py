"""What is newer than the versions a uv.lock pins, as findings for the report.

The action runs two uv commands first. ``uv lock --upgrade --dry-run`` moves
every package as far as the bounds in pyproject.toml allow and prints the
moves without writing the lockfile. ``uv tree --frozen --outdated
--universal`` names the newest release of each package, for every platform
and Python version the lockfile covers. This reads both and the lockfile and
writes findings.jsonl and status.json, as FORMAT.md of the report action
describes.

The lockfile says which packages the repository names itself (direct), which
it needs at runtime and which only in development, and which of its own
packages need a finding. The graph is followed through extras as well, a
dependency entry with ``extra`` leads to the target's optional dependencies.
A package pinned in two versions for different markers is two findings, with
one dry-run line for both and no latest release in the tree, so whether the
bounds allow its newest release stays unknown. The repository's own packages,
the workspace members or the one project, are never a finding.

The build backends come from ``[build-system] requires`` of every
pyproject.toml. An exact pin is compared with the newest release on PyPI, an
unpinned backend floats and is left out.

LOCKFILE, UPGRADE and OUTDATED name the three files, FINDINGS the folder to
write, ROOT the repository (default the working directory). Standard library
only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Fetch = Callable[[str], bytes]
PYPI = "https://pypi.org/pypi"
SKIPPED_FOLDERS = {".git", ".venv", "node_modules", "__pycache__"}

_UPGRADE = re.compile(r"^\s*Updated?\s+(\S+)\s+(.+?)\s+->\s+(.+?)\s*$")
_OUTDATED = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])? v(\S+) .*\(latest: v([^)]+)\)"
)
_PIN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;,\[\]]+)\s*$")


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Dependency:
    name: str
    version: str | None
    extras: tuple[str, ...]


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    root: bool
    dependencies: tuple[Dependency, ...]
    extras: dict[str, tuple[Dependency, ...]] = field(default_factory=dict)
    groups: dict[str, tuple[Dependency, ...]] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return (self.name, self.version)


@dataclass(frozen=True)
class Lock:
    packages: tuple[Package, ...]
    roots: tuple[Package, ...]
    manifest_groups: dict[str, tuple[Dependency, ...]]

    def named(self, dependency: Dependency) -> list[Package]:
        """The packages a dependency entry can mean, all forks unless it names
        one version."""
        return [
            p
            for p in self.packages
            if p.name == dependency.name
            and (dependency.version is None or p.version == dependency.version)
        ]


def _dependencies(entries: Iterable[dict[str, Any]]) -> tuple[Dependency, ...]:
    return tuple(
        Dependency(normalized(e["name"]), e.get("version"), tuple(e.get("extra", [])))
        for e in entries
    )


def _groups(table: dict[str, Any]) -> dict[str, tuple[Dependency, ...]]:
    return {group: _dependencies(entries) for group, entries in table.items()}


def load_lock(text: str) -> Lock:
    """The packages of a lockfile and which of them are the repository's own.

    In a workspace the roots are ``manifest.members``. A single project is the
    package whose source is ``editable = "."`` or ``virtual = "."``.
    """
    data = tomllib.loads(text)
    members = {normalized(m) for m in data.get("manifest", {}).get("members", [])}
    packages = []
    for entry in data.get("package", []):
        source = entry.get("source", {})
        name = normalized(entry["name"])
        root = name in members or "." in (source.get("editable"), source.get("virtual"))
        packages.append(
            Package(
                name=name,
                version=str(entry.get("version", "")),
                root=root,
                dependencies=_dependencies(entry.get("dependencies", [])),
                extras=_groups(entry.get("optional-dependencies", {})),
                groups=_groups(entry.get("dev-dependencies", {})),
            )
        )
    return Lock(
        packages=tuple(packages),
        roots=tuple(p for p in packages if p.root),
        manifest_groups=_groups(data.get("manifest", {}).get("dependency-groups", {})),
    )


def reach(
    lock: Lock, starts: Iterable[tuple[Package, tuple[str, ...]]]
) -> set[tuple[str, str]]:
    """Every package reachable from ``starts``, each a package with the extras
    asked of it, following extras along the way."""
    seen: set[tuple[str, str, str]] = set()
    todo = [(package, extra) for package, extras in starts for extra in ("", *extras)]
    while todo:
        package, extra = todo.pop()
        if (package.name, package.version, extra) in seen:
            continue
        seen.add((package.name, package.version, extra))
        edges = package.dependencies if extra == "" else package.extras.get(extra, ())
        for dependency in edges:
            for target in lock.named(dependency):
                todo += [(target, e) for e in ("", *dependency.extras)]
    return {(name, version) for name, version, _ in seen}


def _runtime_starts(roots: Iterable[Package]) -> list[tuple[Package, tuple[str, ...]]]:
    return [(r, tuple(e for e in r.extras if e != "dev")) for r in roots]


def _dev_starts(lock: Lock) -> list[tuple[Package, tuple[str, ...]]]:
    """The dev extra and every dependency group of the roots, and the groups
    of a workspace root without a package of its own."""
    starts: list[tuple[Package, tuple[str, ...]]] = []
    entries: list[Dependency] = list(
        d for deps in lock.manifest_groups.values() for d in deps
    )
    for root in lock.roots:
        if "dev" in root.extras:
            starts.append((root, ("dev",)))
        entries += [d for deps in root.groups.values() for d in deps]
    for dependency in entries:
        starts += [(target, dependency.extras) for target in lock.named(dependency)]
    return starts


def direct_names(lock: Lock) -> set[str]:
    """The packages the repository names itself, in any scope."""
    names: set[str] = set()
    for root in lock.roots:
        names |= {d.name for d in root.dependencies}
        names |= {d.name for deps in root.extras.values() for d in deps}
        names |= {d.name for deps in root.groups.values() for d in deps}
    names |= {d.name for deps in lock.manifest_groups.values() for d in deps}
    return names - {r.name for r in lock.roots}


def _versions(text: str) -> list[str]:
    return [v.strip().removeprefix("v") for v in text.split(",")]


def parse_upgrade(text: str) -> dict[tuple[str, str], str]:
    """``(name, current) -> newest within bounds`` from the dry run.

    A package pinned in two versions for different markers is one line with
    two versions on each side, ``v2.10, v4.0 -> v2.10, v4.0.1``, matched by
    position. A position that did not move is no move. A line whose sides
    differ in length pairs nothing, the forks changed, and is left out.
    """
    moves = {}
    for line in text.splitlines():
        match = _UPGRADE.match(line)
        if not match:
            continue
        before, after = _versions(match[2]), _versions(match[3])
        if len(before) != len(after):
            continue
        for old, new in zip(before, after, strict=True):
            if old != new:
                moves[(normalized(match[1]), old)] = new
    return moves


def parse_outdated(text: str) -> dict[tuple[str, str], str]:
    """``(name, current) -> latest release`` from the tree."""
    latest = {}
    for line in text.splitlines():
        match = _OUTDATED.search(line)
        if match:
            latest[(normalized(match[1]), match[2])] = match[3]
    return latest


def package_findings(
    lock: Lock,
    upgrade: dict[tuple[str, str], str],
    outdated: dict[tuple[str, str], str],
    where: str,
) -> list[dict[str, Any]]:
    runtime = reach(lock, _runtime_starts(lock.roots))
    dev = reach(lock, _dev_starts(lock))
    direct = direct_names(lock)
    # What a member needs without its extras. A member that asks for an
    # extra of another member is the one that needs what the extra brings.
    needed_by: dict[tuple[str, str], list[str]] = defaultdict(list)
    if len(lock.roots) > 1:
        for root in lock.roots:
            for key in reach(lock, [(root, ())]):
                needed_by[key].append(root.name)
    # The tree names no latest release for a package pinned in several
    # versions, so for one of those the dry run is the only source and
    # whether the bounds allow the newest release stays unknown.
    forks = {
        name
        for name, count in Counter(p.name for p in lock.packages).items()
        if count > 1
    }
    findings = []
    for package in lock.packages:
        if package.root or not package.version:
            continue
        within = upgrade.get(package.key)
        latest = outdated.get(package.key)
        if within is None and latest is None:
            continue
        newest = latest or within
        finding: dict[str, Any] = {
            "category": "package",
            "name": package.name,
            "where": [where],
            "current": package.version,
            "newest": newest,
            "direct": package.name in direct,
            "scope": "runtime"
            if package.key in runtime or package.key not in dev
            else "dev",
        }
        if latest is not None or package.name not in forks:
            finding["within_bounds"] = within is not None and newest == within
        if needed_by:
            finding["packages"] = sorted(needed_by.get(package.key, []))
        findings.append(finding)
    return findings


def pyproject_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("pyproject.toml")
        if not SKIPPED_FOLDERS & set(p.relative_to(root).parts)
    )


def pinned_backends(
    root: Path, files: Iterable[Path]
) -> dict[tuple[str, str], list[str]]:
    """``(name, version) -> files`` for every exact pin in ``[build-system]``."""
    pins: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path in files:
        data = tomllib.loads(path.read_text("utf-8"))
        for requirement in data.get("build-system", {}).get("requires", []):
            match = _PIN.match(requirement)
            if match:
                key = (normalized(match[1]), match[2])
                pins[key].append(path.relative_to(root).as_posix())
    return dict(pins)


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body: bytes = response.read()
        return body


def newest_on_pypi(fetch: Fetch, name: str) -> str:
    data = json.loads(fetch(f"{PYPI}/{name}/json"))
    version: str = data["info"]["version"]
    return version


def backend_findings(
    pins: dict[tuple[str, str], list[str]], fetch: Fetch
) -> list[dict[str, Any]]:
    findings = []
    newest_of: dict[str, str] = {}
    for (name, version), files in sorted(pins.items()):
        if name not in newest_of:
            newest_of[name] = newest_on_pypi(fetch, name)
        if newest_of[name] != version:
            findings.append(
                {
                    "category": "package",
                    "name": name,
                    "where": files,
                    "current": version,
                    "newest": newest_of[name],
                    "direct": True,
                    "scope": "build",
                }
            )
    return findings


def write(
    folder: Path, findings: list[dict[str, Any]], checked: int, packages: list[str]
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(f, sort_keys=True) + "\n" for f in findings)
    (folder / "findings.jsonl").write_text(lines, "utf-8")
    status = {"result": "ok", "checked": checked, "packages": packages}
    (folder / "status.json").write_text(json.dumps(status) + "\n", "utf-8")


def main() -> int:
    root = Path(os.environ.get("ROOT") or Path.cwd())
    lockfile = Path(os.environ.get("LOCKFILE") or root / "uv.lock")
    findings_folder = Path(os.environ["FINDINGS"])
    try:
        lock = load_lock(lockfile.read_text("utf-8"))
        if not lock.roots:
            print(f"::error::{lockfile} names no project and no workspace members.")
            return 1
        upgrade = parse_upgrade(Path(os.environ["UPGRADE"]).read_text("utf-8"))
        outdated = parse_outdated(Path(os.environ["OUTDATED"]).read_text("utf-8"))
        where = lockfile.name if lockfile.is_absolute() else lockfile.as_posix()
        findings = package_findings(lock, upgrade, outdated, where)
        pins = pinned_backends(root, pyproject_files(root))
        findings += backend_findings(pins, fetch_url)
    except (OSError, ValueError, KeyError, urllib.error.URLError) as error:
        print(f"::error::Could not read what is pinned: {error}", file=sys.stderr)
        return 1
    checked = sum(1 for p in lock.packages if not p.root and p.version) + len(pins)
    write(findings_folder, findings, checked, [r.name for r in lock.roots])
    print(f"{checked} pins checked, {len(findings)} findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
