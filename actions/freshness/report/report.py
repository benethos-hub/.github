"""The Markdown of the freshness issue, from the findings of the other jobs.

Each measuring job of freshness.yml leaves an artifact freshness-<job> with
status.json, findings.jsonl and section.md, as FORMAT.md next to this file
describes. This reads every artifact in RESULTS, drops what the caller's
IGNORE patterns name, hides development packages unless DEV is true, and
writes REPORT. An empty report means there is nothing to say, and the issue
closes.

EXPECTED names the jobs that must have left a result. One that did not is a
line in the report, never an empty report, so a run that proved nothing cannot
close an open issue. A job may address a second issue, the alarm, through the
issue field of its status. Its findings and its section go to ALARM instead,
and GITHUB_OUTPUT gets alarm=ready or alarm=skip: skip when a job could not
prove anything, so the alarm issue is left as it was. Only names, versions and
the result of a job go in, the issue is public. Standard library only.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATEGORIES = ("vulnerability", "image", "action", "package")
KINDS = ("major", "minor", "patch", "rebuild", "unknown")
SCOPES = ("runtime", "dev", "build")
ISSUES = ("report", "alarm")
PREFIX = "freshness-"


@dataclass(frozen=True)
class Finding:
    category: str
    name: str
    where: tuple[str, ...]
    current: str
    newest: str
    kind: str
    direct: bool
    scope: str
    packages: tuple[str, ...]
    within_bounds: bool | None
    vulnerability: str
    fix: tuple[str, ...]


@dataclass(frozen=True)
class Result:
    job: str
    state: str
    """``ok``, ``inconclusive``, ``failed`` or ``missing``."""
    checked: int
    packages: tuple[str, ...]
    findings: tuple[Finding, ...]
    issue: str = "report"
    section: str = ""


_HEX = re.compile(r"(sha\d+:)?[0-9a-f]*[a-f][0-9a-f]*")


def _numbers(version: str) -> list[int]:
    """The numbers of a version. A digest or a commit has none."""
    if _HEX.fullmatch(version):
        return []
    return [int(part) for part in re.findall(r"\d+", version)]


def _looks_like_a_date(numbers: list[int]) -> bool:
    return numbers[0] >= 1000 or any(n >= 10_000_000 for n in numbers)


def kind(current: str, newest: str) -> str:
    """How far ``newest`` lies from ``current``, by the numbers in them."""
    before, after = _numbers(current), _numbers(newest)
    if not before or not after:
        return "unknown"
    if _looks_like_a_date(before) or _looks_like_a_date(after):
        return "unknown"
    if before[0] != after[0]:
        return "major"
    if (before + [0])[1] != (after + [0])[1]:
        return "minor"
    return "patch" if before != after else "unknown"


def _strings(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{field} must be a list of strings, not {value!r}")
    return tuple(value)


def _one_of(value: Any, field: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise ValueError(f"{field} must be one of {', '.join(allowed)}, not {value!r}")
    return str(value)


def parse_finding(data: dict[str, Any]) -> Finding:
    """One line of findings.jsonl, or ValueError naming what is wrong."""
    category = _one_of(data.get("category"), "category", CATEGORIES)
    for field in ("name", "current"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise ValueError(f"{field} must be a non-empty string: {data!r}")
    where = _strings(data.get("where"), "where")
    if not where:
        raise ValueError(f"where must name at least one file: {data!r}")
    newest = data.get("newest", "")
    if category != "vulnerability" and not newest:
        raise ValueError(f"newest is missing: {data!r}")
    vulnerability = data.get("vulnerability", "")
    if category == "vulnerability" and not vulnerability:
        raise ValueError(f"vulnerability is missing: {data!r}")
    if "kind" in data:
        found_kind = _one_of(data["kind"], "kind", KINDS)
    else:
        found_kind = kind(data["current"], newest) if newest else "unknown"
    direct = data.get("direct", True)
    within = data.get("within_bounds")
    if not isinstance(direct, bool) or within not in (None, True, False):
        raise ValueError(f"direct and within_bounds must be booleans: {data!r}")
    return Finding(
        category=category,
        name=data["name"],
        where=where,
        current=data["current"],
        newest=str(newest),
        kind=found_kind,
        direct=direct,
        scope=_one_of(data.get("scope", ""), "scope", ("", *SCOPES)),
        packages=_strings(data.get("packages", []), "packages"),
        within_bounds=within,
        vulnerability=str(vulnerability),
        fix=_strings(data.get("fix", []), "fix"),
    )


def _read_result(job: str, folder: Path) -> Result:
    """A job's artifact. status.json decides, findings.jsonl and section.md
    are optional."""
    status_file = folder / "status.json"
    if not folder.is_dir():
        return Result(job, "missing", 0, (), ())
    if not status_file.is_file():
        return Result(job, "failed", 0, (), ())
    status = json.loads(status_file.read_text("utf-8"))
    if not isinstance(status, dict):
        raise ValueError(f"{status_file} is not an object")
    findings: tuple[Finding, ...] = ()
    findings_file = folder / "findings.jsonl"
    if findings_file.is_file():
        findings = tuple(
            parse_finding(json.loads(line))
            for line in findings_file.read_text("utf-8").splitlines()
            if line.strip()
        )
    section_file = folder / "section.md"
    section = section_file.read_text("utf-8").strip() if section_file.is_file() else ""
    checked = status.get("checked", 0)
    if not isinstance(checked, int):
        raise ValueError(f"checked in {status_file} is not a number")
    result = status.get("result")
    return Result(
        job=job,
        state=result if result in ("ok", "inconclusive") else "failed",
        checked=checked,
        packages=_strings(status.get("packages", []), "packages"),
        findings=findings,
        issue=_one_of(status.get("issue", "report"), "issue", ISSUES),
        section=section,
    )


def load_results(results: Path, expected: list[str]) -> list[Result]:
    """Every expected job, then every other artifact found, each once."""
    jobs = list(expected)
    if results.is_dir():
        for folder in sorted(results.iterdir()):
            name = folder.name.removeprefix(PREFIX)
            if folder.is_dir() and folder.name != name and name not in jobs:
                jobs.append(name)
    return [_read_result(job, results / f"{PREFIX}{job}") for job in jobs]


def alarm_ready(results: list[Result]) -> bool:
    """Whether this run may touch the alarm issue. Not when a job could not
    prove anything, when a job of the alarm failed, or when an expected job
    left nothing, since its issue is then unknown."""
    for result in results:
        if result.state in ("inconclusive", "missing"):
            return False
        if result.issue == "alarm" and result.state != "ok":
            return False
    return True


def cell(text: str) -> str:
    """A value from a registry or an index, made safe for a table cell."""
    return re.sub(r"\s+", " ", text).replace("|", "\\|").replace("`", "'").strip()


def _code(text: str) -> str:
    return f"`{cell(text)}`"


def _yes_no(value: bool | None) -> str:
    return "" if value is None else ("yes" if value else "no")


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _where(finding: Finding) -> str:
    return ", ".join(_code(path) for path in finding.where)


def _package_rows(
    findings: list[Finding], packages_column: bool
) -> tuple[list[str], list[list[str]]]:
    header = ["Package", "Pinned", "Newest", "Kind", "Direct", "Within bounds"]
    rows = []
    for f in sorted(findings, key=lambda f: (f.name, f.current)):
        row = [
            _code(f.name),
            cell(f.current),
            cell(f.newest),
            f.kind,
            _yes_no(f.direct),
            _yes_no(f.within_bounds),
        ]
        if packages_column:
            row.append(", ".join(_code(p) for p in f.packages))
        rows.append(row)
    if packages_column:
        header.append("Needed by")
    return header, rows


def _pin_rows(findings: list[Finding]) -> list[list[str]]:
    return [
        [_code(f.name), cell(f.current), cell(f.newest), f.kind, _where(f)]
        for f in sorted(findings, key=lambda f: (f.name, f.current))
    ]


def _vulnerability_rows(
    findings: list[Finding], packages_column: bool
) -> tuple[list[str], list[list[str]]]:
    header = ["Package", "Pinned", "Advisory", "Fixed in", "Scope"]
    rows = []
    for f in sorted(findings, key=lambda f: (f.name, f.vulnerability)):
        row = [
            _code(f.name),
            cell(f.current),
            cell(f.vulnerability),
            ", ".join(cell(v) for v in f.fix),
            f.scope,
        ]
        if packages_column:
            row.append(", ".join(_code(p) for p in f.packages))
        rows.append(row)
    if packages_column:
        header.append("Needed by")
    return header, rows


def _named_one_by_one(finding: Finding) -> bool:
    if finding.category != "package":
        return True
    if finding.scope == "build":
        return True
    return finding.direct or finding.kind == "major"


_WHAT = {
    "missing": "left no result",
    "failed": "failed",
    "inconclusive": "ran but could not prove anything",
}


def render(
    results: list[Result],
    ignore: list[str],
    dev: bool,
    run_url: str = "",
    issue: str = "report",
) -> str:
    """The Markdown for ``issue``, or an empty string when there is nothing
    to say. The lines about jobs without a result go to the report only."""
    without_result = [r for r in results if r.state != "ok" and issue == "report"]
    packages_column = len({p for r in results for p in r.packages}) > 1
    own = [r for r in results if r.issue == issue]

    ignored = 0
    hidden_dev = 0
    counted = 0
    listed: dict[str, list[Finding]] = {c: [] for c in CATEGORIES}
    build: list[Finding] = []
    development: list[Finding] = []
    for result in own:
        for finding in result.findings:
            if any(fnmatch.fnmatchcase(finding.name, p) for p in ignore):
                ignored += 1
            elif finding.category == "package" and finding.scope == "dev":
                if not dev:
                    hidden_dev += 1
                elif _named_one_by_one(finding):
                    development.append(finding)
                else:
                    counted += 1
            elif finding.category == "package" and finding.scope == "build":
                build.append(finding)
            elif _named_one_by_one(finding):
                listed[finding.category].append(finding)
            else:
                counted += 1
    prose = [r for r in own if r.section]

    tables = any(listed.values()) or build or development
    if not (tables or prose or without_result):
        return ""

    lines: list[str] = []
    if without_result:
        for result in without_result:
            run = f" See [the run]({run_url})." if run_url else ""
            lines.append(
                f"- The job {_code(result.job)} {_WHAT[result.state]}, so its "
                f"part of this report is missing.{run}"
            )
        lines.append("")

    sections = [
        ("Known vulnerabilities", listed["vulnerability"]),
        ("Images", listed["image"]),
        ("Actions", listed["action"]),
        ("Build backends", build),
        ("Packages", listed["package"]),
        ("Development packages", development),
    ]
    for title, findings in sections:
        if not findings:
            continue
        lines += [f"### {title}", ""]
        if title == "Known vulnerabilities":
            header, rows = _vulnerability_rows(findings, packages_column)
        elif title in ("Packages", "Development packages"):
            header, rows = _package_rows(findings, packages_column)
        else:
            header = ["Name", "Pinned", "Newest", "Kind", "Where"]
            rows = _pin_rows(findings)
        lines += _table(header, rows)
        lines.append("")

    # The prose of a job comes after the tables, under the name of the job.
    for result in prose:
        lines += [f"### {result.job}", "", result.section, ""]

    notes = []
    if counted:
        notes.append(
            f"{counted} more transitive, each a minor, a patch or an unknown kind."
        )
    if hidden_dev:
        notes.append(f"{hidden_dev} development packages are not shown.")
    if ignored:
        notes.append(f"{ignored} findings match the ignore patterns of the caller.")
    if notes:
        lines += [" ".join(notes), ""]
    if tables:
        lines.append(
            "Versions are measured at their source, the package index, the registry "
            "or the API. Kind, scope and the counts are derived from them. Image "
            "tags of the same digit form are assumed to be one series."
        )
    return "\n".join(lines).rstrip("\n") + "\n"


def _words(value: str) -> list[str]:
    return value.split()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def main() -> int:
    results = Path(os.environ.get("RESULTS", ""))
    report = Path(os.environ["REPORT"])
    alarm = os.environ.get("ALARM", "")
    expected = _words(os.environ.get("EXPECTED", ""))
    ignore = _words(os.environ.get("IGNORE", ""))
    dev = os.environ.get("DEV", "false").lower() == "true"
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = f"{server}/{repository}/actions/runs/{run_id}" if run_id else ""
    try:
        loaded = load_results(results, expected)
        text = render(loaded, ignore, dev, run_url)
        alarm_text = render(loaded, ignore, dev, run_url, "alarm")
    except (ValueError, OSError) as error:
        print(f"::error::Could not read the findings: {error}", file=sys.stderr)
        return 1
    _write(report, text)
    for result in loaded:
        print(f"{result.job}: {result.state}, {len(result.findings)} findings")
    print("Nothing to report." if not text else f"Report written to {report}.")
    if alarm:
        _write(Path(alarm), alarm_text)
        ready = alarm_ready(loaded)
        print(
            f"Alarm written to {alarm}, "
            + ("ready for its issue." if ready else "a job could not prove anything.")
        )
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as handle:
                handle.write(f"alarm={'ready' if ready else 'skip'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
