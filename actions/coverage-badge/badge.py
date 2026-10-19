"""Write the JSON of a coverage badge from a percentage.

A test workflow measures the coverage in whatever way its language has,
python-tests.yml with coverage.py, and hands the percentage to this script
through the action next to it. The JSON is what shields.io renders as a
badge, and coverage-badge.yml publishes it on the badges branch of the
repository, where the README embeds it:

    https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/<owner>/<repo>/badges/coverage.json

    badge.py <percent> <badge.json>

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
    try:
        percent = float(argv[0])
    except ValueError:
        percent = math.nan
    if not 0 <= percent <= 100:
        print(f"::error::{argv[0]!r} is not a percentage between 0 and 100.")
        return 1
    result = badge(percent)
    target = Path(argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result) + "\n", "utf-8")
    print(f"coverage {percent:.1f}%, badge {result['message']} {result['color']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
