"""Summarise a SARIF file for the step summary and say whether it fails the step.

SARIF is what the scanners here write and what code scanning reads. The
script reads one file, counts the results by level, writes a table to the
step summary, sets the outputs and says whether a result reaches the level
that fails the step. The step itself fails later, after the upload, so the
findings are in code scanning either way.

Environment: SARIF names the file, TOOL the heading (empty takes the name in
the file), FAILURE_LEVEL is none, note, warning or error, ROWS how many
findings the summary lists (default 50). GITHUB_STEP_SUMMARY and
GITHUB_OUTPUT are the files of the runner.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LEVELS = ("note", "warning", "error")
RANK = {"none": 0, "note": 1, "warning": 2, "error": 3}


@dataclass(frozen=True)
class Finding:
    level: str
    rule: str
    where: str
    message: str


def findings(sarif: dict[str, Any]) -> tuple[str, list[Finding]]:
    """The tool named in the file and every result of every run.

    A result without a level takes the default of its rule, and warning
    without that, as SARIF says. A result of level none is no finding.
    """
    tool = ""
    found: list[Finding] = []
    for run in sarif.get("runs", []):
        driver = run.get("tool", {}).get("driver", {})
        tool = tool or str(driver.get("name", ""))
        rules = {r.get("id"): r for r in driver.get("rules", [])}
        for result in run.get("results", []):
            rule = str(result.get("ruleId", ""))
            level = result.get("level") or rules.get(rule, {}).get(
                "defaultConfiguration", {}
            ).get("level")
            level = str(level or "warning")
            if level not in LEVELS:
                continue
            where = ""
            for location in result.get("locations", [])[:1]:
                physical = location.get("physicalLocation", {})
                uri = str(physical.get("artifactLocation", {}).get("uri", ""))
                line = physical.get("region", {}).get("startLine")
                where = f"{uri}:{line}" if line else uri
            text = str(result.get("message", {}).get("text", ""))
            message = text.splitlines()[0] if text else ""
            found.append(Finding(level, rule, where, message))
    return tool, found


def counts(found: list[Finding]) -> dict[str, int]:
    return {level: sum(1 for f in found if f.level == level) for level in LEVELS}


def highest(found: list[Finding]) -> str:
    return max((f.level for f in found), key=RANK.__getitem__, default="none")


def fails(found: list[Finding], failure_level: str) -> bool:
    """Whether a finding reaches ``failure_level``. none never fails."""
    if failure_level == "none":
        return False
    return any(RANK[f.level] >= RANK[failure_level] for f in found)


def summary(tool: str, found: list[Finding], rows: int) -> str:
    """The Markdown for the step summary."""
    by_level = counts(found)
    lines = [f"### {tool}: {len(found)} finding{'' if len(found) == 1 else 's'}", ""]
    if not found:
        lines.append("Nothing to report.")
        return "\n".join(lines) + "\n"
    lines.append(", ".join(f"{by_level[level]} {level}" for level in reversed(LEVELS)))
    lines += ["", "| Level | Rule | Where | Message |", "| --- | --- | --- | --- |"]
    ordered = sorted(found, key=lambda f: (-RANK[f.level], f.where, f.rule))
    for f in ordered[:rows]:
        message = f.message.replace("|", "\\|")
        lines.append(f"| {f.level} | {f.rule} | `{f.where}` | {message} |")
    if len(found) > rows:
        lines += ["", f"{len(found) - rows} more in the SARIF file."]
    return "\n".join(lines) + "\n"


def main() -> int:
    path = Path(os.environ.get("SARIF", ""))
    failure_level = os.environ.get("FAILURE_LEVEL") or "none"
    if failure_level not in RANK:
        print(
            f"::error::failure-level is {failure_level}, it has to be one of "
            f"{', '.join(RANK)}."
        )
        return 1
    if not path.is_file():
        print(f"::error::{path} is not a file. The scanner left no SARIF.")
        return 1
    try:
        sarif = json.loads(path.read_text("utf-8"))
    except ValueError as error:
        print(f"::error::{path} is not JSON: {error}")
        return 1
    named, found = findings(sarif)
    tool = os.environ.get("TOOL") or named or "Scanner"
    rows = int(os.environ.get("ROWS") or 50)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write(summary(tool, found, rows))
    outputs = {
        "findings": str(len(found)),
        **{f"{level}s": str(n) for level, n in counts(found).items()},
        "highest": highest(found),
        "fail": str(fails(found, failure_level)).lower(),
    }
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.writelines(f"{key}={value}\n" for key, value in outputs.items())
    print(f"{tool}: {len(found)} findings, highest {outputs['highest']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
