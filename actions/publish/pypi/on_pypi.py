"""Warn in a trial run when the version just built is on PyPI already.

A trial run started by hand usually builds the version of the last release,
because the version is raised in the release commit. That is fine for the
trial, so this only warns that a release of this version would be refused.
It never fails, not even when PyPI cannot be reached.

DIST names the folder uv build wrote, which check_dist.py has checked to
hold one wheel. Standard library only.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

API = "https://pypi.org/pypi/{name}/{version}/json"

Fetch = Callable[[str], int]


def _status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            status: int = response.status
            return status
    except urllib.error.HTTPError as error:
        return error.code


def warn(dist: Path, fetch: Fetch = _status) -> None:
    (wheel,) = dist.glob("*.whl")
    name, version = wheel.name.split("-")[:2]
    try:
        status = fetch(API.format(name=name, version=version))
    except urllib.error.URLError as error:
        print(f"::warning::Could not ask PyPI whether {version} is released: {error}")
        return
    if status == 200:
        print(
            f"::warning title=Version {version} is on PyPI already::"
            f"{wheel.name} is version {version}, which is on PyPI already. "
            "A release needs a new version first."
        )
    elif status == 404:
        print(f"Version {version} is not on PyPI yet.")
    else:
        print(f"::warning::PyPI answered {status} for version {version}.")


def main() -> int:
    warn(Path(os.environ["DIST"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
