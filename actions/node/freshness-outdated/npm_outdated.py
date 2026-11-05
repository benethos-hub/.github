"""What is newer than the versions a package-lock.json pins, for the report.

``npm outdated`` compares with the dist-tag ``latest``, which can be older than
the pin, so it never names a newer release on the line the repository is on.
Newest here is the highest version in the package's list of versions that has
no pre-release part and is not deprecated, compared by semver. A finding is
written only when newest is higher than the locked version, so a new release on
an older line is none.

The abbreviated document of the registry lists every version with its deprecated
mark. It has no version ranges to resolve here, so ``within_bounds`` is left out.

``direct`` comes from the root entry of the lockfile, so what only a workspace
member names counts as transitive. A package locked at one version in several
folders is one finding, needed at runtime when any of its entries is. An entry
with ``dev`` is development only, ``devOptional`` can be needed at runtime.

Entries that do not come from the registry, a link, a git or file source, another
host or a package bundled inside its parent, are no finding and are counted in the
summary. A package the registry does not know, unpublished or private, is a
warning and counted as well. A registry that cannot be reached, a rate limit or a
5xx leaves the status inconclusive and no findings.jsonl, so a run that proved
nothing never closes the issue. A lockfile that cannot be read is a failure.

LOCKFILE names the lockfile, relative to ROOT (default the working directory),
FINDINGS the folder to write. Standard library only. Runs no code of a package.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

Fetch = Callable[[str], tuple[int, bytes]]
VersionKey = tuple[int, int, int, int, tuple[tuple[int, int, str], ...]]

REGISTRY = "https://registry.npmjs.org"
ABBREVIATED = "application/vnd.npm.install-v1+json"
NODE_MODULES = "node_modules/"

_SEMVER = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


class Unreachable(Exception):
    """The registry gave no answer to go by. The message is public."""


def version_key(version: str) -> VersionKey | None:
    """A sort key by the precedence of semver, None for anything else. A
    pre-release sorts below its release, numeric identifiers as numbers and
    below text ones, a shorter list of identifiers below a longer one."""
    match = _SEMVER.match(version)
    if not match:
        return None
    major, minor, patch = int(match[1]), int(match[2]), int(match[3])
    if match[4] is None:
        return (major, minor, patch, 1, ())
    identifiers = tuple(
        (0, int(part), "") if part.isdecimal() else (1, 0, part)
        for part in match[4].split(".")
    )
    return (major, minor, patch, 0, identifiers)


def newest_stable(versions: dict[str, Any]) -> str | None:
    """The highest version without a pre-release part that is not deprecated."""
    best: tuple[VersionKey, str] | None = None
    for version, data in versions.items():
        key = version_key(version)
        if key is None or key[3] == 0 or data.get("deprecated"):
            continue
        if best is None or key > best[0]:
            best = (key, version)
    return best[1] if best else None


def read_lockfile(path: Path) -> dict[str, dict[str, Any]]:
    """The ``packages`` of a lockfile. Raises OSError or ValueError."""
    data = json.loads(path.read_text("utf-8"))
    packages = data.get("packages") if isinstance(data, dict) else None
    if not isinstance(packages, dict):
        raise ValueError(
            "it has no packages key, as a lockfile of version 1. "
            "npm install --package-lock-only with npm 7 or newer rewrites it."
        )
    return packages


def from_registry(entry: dict[str, Any]) -> bool:
    """Whether the entry is a version of the public registry. A lockfile written
    with omit-lockfile-registry-resolved names no source for those."""
    if entry.get("link") or entry.get("inBundle"):
        return False
    if version_key(str(entry.get("version", ""))) is None:
        return False
    resolved = entry.get("resolved")
    return resolved is None or str(resolved).startswith(f"{REGISTRY}/")


def versions_of(name: str, fetch: Fetch) -> dict[str, Any] | None:
    """The versions the registry lists, None when it does not know the package."""
    url = f"{REGISTRY}/{urllib.parse.quote(name, safe='@')}"
    try:
        status, body = fetch(url)
    except (OSError, http.client.HTTPException) as error:
        raise Unreachable(f"The npm registry could not be reached: {name}") from error
    if status == 404:
        return None
    if status != 200:
        raise Unreachable(f"The npm registry answered {status}: {name}")
    try:
        data = json.loads(body)
    except ValueError as error:
        raise Unreachable(f"The npm registry sent nothing readable: {name}") from error
    if not isinstance(data, dict):
        raise Unreachable(f"The npm registry sent nothing readable: {name}")
    versions = data.get("versions")
    if not versions or not isinstance(versions, dict):
        return None
    if not all(isinstance(v, dict) for v in versions.values()):
        raise Unreachable(f"The npm registry sent nothing readable: {name}")
    return versions


def _locked(
    packages: dict[str, dict[str, Any]],
) -> tuple[dict[tuple[str, str], dict[str, bool]], int]:
    """``(name, version) -> direct, dev`` of the registry entries, and how many
    entries are not from the registry. The root and workspace members are the
    repository's own and neither."""
    root = packages.get("", {})
    named = {
        name
        for field in (
            "dependencies",
            "devDependencies",
            "optionalDependencies",
            "peerDependencies",
        )
        for name in root.get(field, {})
    }
    locked: dict[tuple[str, str], dict[str, bool]] = {}
    left_out = 0
    for path, entry in packages.items():
        if NODE_MODULES not in path:
            continue
        if not from_registry(entry):
            left_out += 1
            continue
        installed_as = path.rsplit(NODE_MODULES, 1)[1]
        # An alias is installed under one name and is another package.
        key = (str(entry.get("name") or installed_as), str(entry["version"]))
        seen = locked.setdefault(key, {"direct": False, "dev": True})
        seen["direct"] |= path == NODE_MODULES + installed_as and installed_as in named
        seen["dev"] &= entry.get("dev") is True
    return locked, left_out


def measure(
    packages: dict[str, dict[str, Any]], where: str, fetch: Fetch
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The findings and the status of a run that got its answers."""
    locked, left_out = _locked(packages)
    known: dict[str, dict[str, Any] | None] = {}
    findings = []
    unknown: set[str] = set()
    for (name, version), marks in sorted(locked.items()):
        if name not in known:
            known[name] = versions_of(name, fetch)
        versions = known[name]
        if versions is None:
            unknown.add(name)
            continue
        newest = newest_stable(versions)
        if newest is None:
            continue
        newest_key, current_key = version_key(newest), version_key(version)
        assert newest_key and current_key
        if newest_key > current_key:
            findings.append(
                {
                    "category": "package",
                    "name": name,
                    "where": [where],
                    "current": version,
                    "newest": newest,
                    "direct": marks["direct"],
                    "scope": "dev" if marks["dev"] else "runtime",
                }
            )
    for name in sorted(unknown):
        print(f"::warning::The npm registry does not know {name}, it was not checked.")
    checked = len(locked)
    compared = checked - sum(name in unknown for name, _ in locked)
    summary = f"{compared} locked package{'' if compared == 1 else 's'}"
    summary += " compared with the npm registry"
    if unknown:
        summary += f", {len(unknown)} not known to it"
    if left_out:
        summary += f", {left_out} {'entry' if left_out == 1 else 'entries'}"
        summary += " not from it left out"
    return findings, {"result": "ok", "checked": checked, "summary": summary + "."}


def fetch_url(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"Accept": ABBREVIATED})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, b""


def write_status(folder: Path, status: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "status.json").write_text(json.dumps(status) + "\n", "utf-8")


def main() -> int:
    root = Path(os.environ.get("ROOT") or Path.cwd())
    lockfile = Path(os.environ.get("LOCKFILE") or "package-lock.json")
    if not lockfile.is_absolute():
        lockfile = root / lockfile
    folder = Path(os.environ["FINDINGS"])
    try:
        packages = read_lockfile(lockfile)
        where = Path(os.path.normpath(lockfile.relative_to(root))).as_posix()
    except (OSError, ValueError) as error:
        print(f"::error::Could not read {lockfile}: {error}", file=sys.stderr)
        return 1
    try:
        findings, status = measure(packages, where, fetch_url)
    except Unreachable as error:
        print(f"::warning::{error}")
        write_status(folder, {"result": "inconclusive", "summary": f"{error}."})
        return 0
    write_status(folder, status)
    lines = "".join(json.dumps(f, sort_keys=True) + "\n" for f in findings)
    (folder / "findings.jsonl").write_text(lines, "utf-8")
    print(f"{status['summary']} {len(findings)} findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
