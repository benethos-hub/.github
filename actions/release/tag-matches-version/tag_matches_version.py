"""Fail a release whose tag is not the version in the given file.

The tag and the version are written in two places. A tag v0.7.0 on a commit
whose pyproject.toml still says 0.6.1 made PyPI refuse the upload, while the
image job pushed 0.7.0, 0.7 and latest with the old code. Run before anything
is built or published.

VERSION_FILE names the file: a pyproject.toml, whose [project] version
counts, or a JSON file such as the manifest of a Claude Desktop bundle or a
server.json for the MCP Registry, whose top-level version counts. TAG holds
the release tag, with or without a leading v. Standard library only.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any


def read_version(path: Path) -> str:
    """The version ``path`` declares, or SystemExit with the reason."""
    text = path.read_text(encoding="utf-8")
    data: Any
    if path.suffix == ".toml":
        data = tomllib.loads(text).get("project", {})
        where = "[project] version"
    elif path.suffix == ".json":
        data = json.loads(text)
        where = "the top-level version"
    else:
        raise SystemExit(f"::error::{path} is neither a .toml nor a .json file.")
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, str) or not version:
        raise SystemExit(f"::error::{path} has no {where}.")
    return version


def check(tag: str, path: Path) -> int:
    version = read_version(path)
    if tag.removeprefix("v") != version:
        print(
            f"::error::Release tag {tag!r} is not the version {version!r} in "
            f"{path}. Bump the version first, or tag v{version}."
        )
        return 1
    print(f"Release tag {tag} matches the version {version} in {path}.")
    return 0


def main() -> int:
    tag = os.environ.get("TAG", "")
    if not tag:
        print("::error::No release tag to compare. Run this on a release.")
        return 1
    return check(tag, Path(os.environ.get("VERSION_FILE") or "pyproject.toml"))


if __name__ == "__main__":
    sys.exit(main())
