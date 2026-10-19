"""Write the JSON of a coverage badge from a coverage.py JSON report.

python-tests.yml measures the coverage on one Python version and, with
badge: true, turns the result into the JSON that shields.io renders as a
badge. python-coverage-badge.yml then publishes that file on the badges
branch of the repository, and the README embeds it:

    https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/<owner>/<repo>/badges/coverage.json

    badge.py <coverage.json> <badge.json>

The percentage is rounded down, so the badge never shows more than was
measured, and a badge at the floor means the floor holds. The colour goes
from red below 50 to bright green from 90 on. Standard library only.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

COLOURS = (
    (90, "brightgreen"),
    (80, "green"),
    (70, "yellowgreen"),
    (60, "yellow"),
    (50, "orange"),
)


def colour(percent: float) -> str:
    for floor, name in COLOURS:
        if percent >= floor:
            return name
    return "red"


def badge(percent: float) -> dict[str, Any]:
    """The endpoint JSON shields.io reads, see shields.io/badges/endpoint-badge."""
    shown = math.floor(percent)
    return {
        "schemaVersion": 1,
        "label": "coverage",
        "message": f"{shown}%",
        "color": colour(shown),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    report, target = Path(argv[0]), Path(argv[1])
    totals = json.loads(report.read_text("utf-8")).get("totals") or {}
    percent = totals.get("percent_covered")
    if not isinstance(percent, (int, float)):
        print(f"::error::{report} has no totals.percent_covered.")
        return 1
    result = badge(float(percent))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result) + "\n", "utf-8")
    print(f"coverage {percent:.1f}%, badge {result['message']} {result['color']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
