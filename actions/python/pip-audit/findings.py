"""The vulnerabilities pip-audit found, as findings for the freshness report.

The action asks two services and splits a name pinned in several versions
into several calls, so WORK holds one JSON file per call. The same
vulnerability carries a PYSEC ID at one service and a GHSA ID at the other,
linked through their aliases, and is one finding here, named by its GHSA ID
where it has one. The fix versions of both are joined.

IGNORE_VULNS drops a finding whose IDs match a waiver, pip-audit itself only
matches the primary ID. PINNED_IN names the file of the repository the
versions come from, FINDINGS the folder to write. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def _chosen_id(ids: set[str]) -> str:
    ghsa = sorted(i for i in ids if i.startswith("GHSA-"))
    return ghsa[0] if ghsa else sorted(ids)[0]


def merge(
    reports: list[dict[str, Any]], pinned_in: str, ignore: set[str]
) -> tuple[list[dict[str, Any]], int]:
    """The findings of every report, one per vulnerability of a pinned
    version, and how many pinned versions were audited."""
    audited: set[tuple[str, str]] = set()
    groups: dict[tuple[str, str], list[tuple[set[str], set[str]]]] = defaultdict(list)
    for report in reports:
        for dependency in report.get("dependencies", []):
            key = (dependency["name"].lower(), dependency["version"])
            audited.add(key)
            for vuln in dependency.get("vulns", []):
                ids = {vuln["id"], *vuln.get("aliases", [])}
                fixes = set(vuln.get("fix_versions", []))
                for known_ids, known_fixes in groups[key]:
                    if known_ids & ids:
                        known_ids |= ids
                        known_fixes |= fixes
                        break
                else:
                    groups[key].append((ids, fixes))
    findings = []
    for (name, version), vulns in sorted(groups.items()):
        for ids, fixes in vulns:
            if ids & ignore:
                continue
            findings.append(
                {
                    "category": "vulnerability",
                    "name": name,
                    "where": [pinned_in],
                    "current": version,
                    "vulnerability": _chosen_id(ids),
                    "fix": sorted(fixes, key=version_key),
                }
            )
    return findings, len(audited)


def main() -> int:
    work = Path(os.environ["WORK"])
    folder = Path(os.environ["FINDINGS"])
    pinned_in = os.environ.get("PINNED_IN") or "uv.lock"
    ignore = set(os.environ.get("IGNORE_VULNS", "").split())
    files = sorted(work.glob("findings-*.json"))
    if not files:
        print(
            f"::error::No pip-audit output in {work}, nothing was audited.",
            file=sys.stderr,
        )
        return 1
    try:
        reports = [json.loads(path.read_text("utf-8")) for path in files]
        findings, checked = merge(reports, pinned_in, ignore)
    except (OSError, ValueError, KeyError) as error:
        print(f"::error::Could not read the pip-audit output: {error}", file=sys.stderr)
        return 1
    folder.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(f, sort_keys=True) + "\n" for f in findings)
    (folder / "findings.jsonl").write_text(lines, "utf-8")
    status = {"result": "ok", "checked": checked}
    (folder / "status.json").write_text(json.dumps(status) + "\n", "utf-8")
    print(f"{checked} pinned versions audited, {len(findings)} known vulnerabilities.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
