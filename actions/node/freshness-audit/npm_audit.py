"""The vulnerabilities npm audit found, as findings for the freshness report.

The action runs ``npm audit --json --package-lock-only`` first and leaves its
output in AUDIT. Each advisory object in ``via`` is one finding per locked version
of that package, named by the GHSA ID of its URL. An entry in ``via`` that is a
plain string only points at another package and is skipped, that package has its
own entry. ``nodes`` names the folders of the lockfile the audit found affected,
without saying which advisory hit which of them. So with two affected versions,
each advisory is named for both.

``fix`` is set only when ``fixAvailable`` names a version of the same package. It
can name the parent that has to move instead, or be a plain ``true``.

The output of a run that got an answer has ``vulnerabilities``. When the endpoint
gave no answer, a refused connection or an error status, npm prints an object with
``message`` and without ``vulnerabilities`` (measured on 2026-11-05 with npm 11.20
against 403, 404, 429, 500 and a closed port). That is inconclusive with no
findings.jsonl, so a run that proved nothing never closes the issue. Anything else,
and a lockfile that cannot be read, is a failure.

LOCKFILE names the lockfile, relative to ROOT (default the working directory),
AUDIT the output of npm audit, IGNORE_VULNS the IDs to waive, FINDINGS the folder
to write. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

NODE_MODULES = "node_modules/"

_GHSA = re.compile(r"GHSA(?:-[0-9A-Za-z]{4}){3}")


class Unreachable(Exception):
    """The audit endpoint gave no answer to go by. The message is public."""


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


def read_audit(text: str) -> dict[str, Any]:
    """The ``vulnerabilities`` of the output. Raises Unreachable when the
    endpoint gave no answer, ValueError for anything else."""
    if not text.strip():
        raise ValueError("npm audit printed nothing")
    report = json.loads(text)
    if not isinstance(report, dict):
        raise ValueError("npm audit printed no object")
    vulnerabilities = report.get("vulnerabilities")
    if isinstance(vulnerabilities, dict):
        return vulnerabilities
    if "message" in report:
        status = report.get("statusCode")
        answered = f" It answered {status}." if isinstance(status, int) else ""
        raise Unreachable(f"The npm audit endpoint gave no result.{answered}")
    error = report.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    raise ValueError(f"npm audit failed: {code or 'no report in its output'}")


def _advisory_id(advisory: dict[str, Any]) -> str:
    url = advisory.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError(f"an advisory without a URL: {advisory.get('source')}")
    match = _GHSA.search(url)
    return match[0] if match else url


def findings_of(
    vulnerabilities: dict[str, Any],
    packages: dict[str, dict[str, Any]],
    where: str,
    ignore: set[str],
) -> list[dict[str, Any]]:
    """One finding per advisory and locked version, without the waived ones."""
    findings = []
    seen: set[tuple[str, str, str]] = set()
    for key, entry in sorted(vulnerabilities.items()):
        name = str(entry.get("name") or key)
        advisories = [a for a in entry.get("via", []) if isinstance(a, dict)]
        if not advisories:
            continue
        versions = sorted(
            {
                str(packages[node]["version"])
                for node in entry.get("nodes", [])
                if "version" in packages.get(node, {})
            }
        )
        if not versions:
            raise ValueError(f"the audit names {name}, the lockfile does not")
        fix = entry.get("fixAvailable")
        for advisory in advisories:
            vulnerability = _advisory_id(advisory)
            if vulnerability in ignore:
                continue
            for version in versions:
                if (name, version, vulnerability) in seen:
                    continue
                seen.add((name, version, vulnerability))
                finding = {
                    "category": "vulnerability",
                    "name": name,
                    "where": [where],
                    "current": version,
                    "vulnerability": vulnerability,
                }
                if (
                    isinstance(fix, dict)
                    and fix.get("name") == name
                    and fix.get("version")
                ):
                    finding["fix"] = [str(fix["version"])]
                findings.append(finding)
    return findings


def checked_of(packages: dict[str, dict[str, Any]]) -> int:
    """How many versions the lockfile pins. A link has no version of its own."""
    return len(
        {
            (path.rsplit(NODE_MODULES, 1)[1], str(entry["version"]))
            for path, entry in packages.items()
            if NODE_MODULES in path and "version" in entry
        }
    )


def write_status(folder: Path, status: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "status.json").write_text(json.dumps(status) + "\n", "utf-8")


def main() -> int:
    root = Path(os.environ.get("ROOT") or Path.cwd())
    lockfile = Path(os.environ.get("LOCKFILE") or "package-lock.json")
    if not lockfile.is_absolute():
        lockfile = root / lockfile
    folder = Path(os.environ["FINDINGS"])
    ignore = set(os.environ.get("IGNORE_VULNS", "").split())
    try:
        packages = read_lockfile(lockfile)
        where = Path(os.path.normpath(lockfile.relative_to(root))).as_posix()
    except (OSError, ValueError) as error:
        print(f"::error::Could not read {lockfile}: {error}", file=sys.stderr)
        return 1
    try:
        vulnerabilities = read_audit(Path(os.environ["AUDIT"]).read_text("utf-8"))
        findings = findings_of(vulnerabilities, packages, where, ignore)
    except Unreachable as error:
        print(f"::warning::{error}")
        write_status(folder, {"result": "inconclusive", "summary": str(error)})
        return 0
    except (OSError, ValueError, AttributeError, TypeError) as error:
        print(f"::error::Could not read the npm audit output: {error}", file=sys.stderr)
        return 1
    checked = checked_of(packages)
    write_status(folder, {"result": "ok", "checked": checked})
    lines = "".join(json.dumps(f, sort_keys=True) + "\n" for f in findings)
    (folder / "findings.jsonl").write_text(lines, "utf-8")
    print(f"{checked} pinned versions audited, {len(findings)} known vulnerabilities.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
