"""Hold a published multi-arch image index to what the package page reads.

Setting the annotations and assuming they arrived is what once produced a
package page reading "No description provided" while the image carried the
description in its configuration all along. So the index is read back from
the registry after the push and checked here: the OCI annotations GitHub
shows, and every platform that was built. Standard library only:

    check_index.py <index.json>

PLATFORMS names the platforms that must be in the index, separated by
commas, as in linux/amd64,linux/arm64.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ANNOTATIONS = (
    "org.opencontainers.image.description",
    "org.opencontainers.image.source",
    "org.opencontainers.image.version",
)


def platforms_of(index: dict[str, Any]) -> list[str]:
    """The platforms in the index. The unknown/unknown entries are the
    provenance attestations, one per real platform, not architectures."""
    return sorted(
        f"{m['platform']['os']}/{m['platform']['architecture']}"
        for m in index.get("manifests", [])
        if m.get("platform", {}).get("architecture") != "unknown"
    )


def problems(index: dict[str, Any], wanted: list[str]) -> list[str]:
    annotations = index.get("annotations") or {}
    found = [
        f"the index carries no {key}, so the package page shows nothing for it"
        for key in ANNOTATIONS
        if not annotations.get(key)
    ]
    have = platforms_of(index)
    found += [
        f"{platform} is missing, the index holds {have}"
        for platform in wanted
        if platform not in have
    ]
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    index: dict[str, Any] = json.loads(Path(argv[0]).read_text("utf-8"))
    wanted = [
        p.strip() for p in os.environ.get("PLATFORMS", "").split(",") if p.strip()
    ]
    found = problems(index, wanted)
    for line in found:
        print(f"::error::{line}")
    if found:
        return 1
    print("OK:", ", ".join(platforms_of(index)))
    print("   ", index["annotations"]["org.opencontainers.image.description"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
