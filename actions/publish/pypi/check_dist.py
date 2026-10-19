"""Check the distributions uv build wrote before they go to PyPI.

A version on PyPI cannot be replaced, so what is uploaded is checked, not
what pyproject.toml says. The folder must hold exactly one wheel and one
sdist. The wheel must be the package asked for, carry the version of the
release tag, and contain every file the repository names. A missing
py.typed, for one, makes type checkers ignore every annotation of the
package, and nothing else would notice.

DIST names the folder, TAG the release tag with or without a leading v,
PACKAGE the distribution (empty for the project in the root), and
WHEEL_CONTAINS the required paths, one per line. {version} in a path stands
for the version, as in a .dist-info folder. Standard library only.
"""

from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def check(dist: Path, tag: str, package: str, contains: list[str]) -> int:
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        found = ", ".join(p.name for p in wheels + sdists) or "nothing"
        print(f"::error::Expected one wheel and one sdist in {dist}, found {found}.")
        return 1
    (wheel,) = wheels
    name, version = wheel.name.split("-")[:2]
    errors = []
    if package and _normalize(name) != _normalize(package):
        errors.append(f"{wheel.name} is not the package {package}.")
    if tag.removeprefix("v") != version:
        errors.append(
            f"{wheel.name} is version {version}, the release tag is {tag}. "
            f"Bump the version first, or tag v{version}."
        )
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    for path in contains:
        wanted = path.replace("{version}", version)
        if wanted not in names:
            errors.append(f"{wheel.name} does not contain {wanted}.")
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1
    print(f"OK: {wheel.name} and {sdists[0].name}, version {version}, {len(names)} files")
    return 0


def main() -> int:
    contains = [line.strip() for line in os.environ.get("WHEEL_CONTAINS", "").splitlines()]
    return check(
        Path(os.environ["DIST"]),
        os.environ.get("TAG", ""),
        os.environ.get("PACKAGE", ""),
        [line for line in contains if line],
    )


if __name__ == "__main__":
    sys.exit(main())
