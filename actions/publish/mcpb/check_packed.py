"""Hold a packed Claude Desktop bundle to the tree it was packed from.

The bundle is packed in a job that can write to the release, and the MCP
Registry entry then vouches for whatever came out by its hash. So the bundle
is unpacked here and compared with the staged tree before anything is
uploaded: the same files, each byte for byte, and nothing else. Standard
library only:

    check_packed.py <staging dir> <bundle.mcpb>
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def staged_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def packed_files(bundle: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(bundle) as packed:
        return {
            info.filename: packed.read(info)
            for info in packed.infolist()
            if not info.is_dir()
        }


def differences(root: Path, bundle: Path) -> list[str]:
    staged = staged_files(root)
    packed = packed_files(bundle)
    found = [f"added by the packer: {name}" for name in sorted(packed.keys() - staged)]
    found += [f"missing from the bundle: {name}" for name in sorted(staged.keys() - packed)]
    found += [
        f"changed by the packer: {name}"
        for name in sorted(staged.keys() & packed)
        if staged[name] != packed[name]
    ]
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    root, bundle = Path(argv[0]), Path(argv[1])
    found = differences(root, bundle)
    for line in found:
        print(f"::error::{line}")
    if found:
        print(f"::error::{bundle.name} is not the staged tree, nothing uploaded.")
        return 1
    print(f"{bundle.name}: {len(staged_files(root))} files, each as staged")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
