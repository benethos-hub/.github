"""Prepare a server.json for the MCP Registry around the Claude Desktop bundle.

The registry wants a fileSha256 for the mcpb package, and that hash exists
only once the release has built the bundle. The committed server.json holds
a placeholder of zeros, and the action downloads the bundle the release
carries and fills in its hash before publishing:

    registry_entry.py bundle-name <server.json>
    registry_entry.py fill <server.json> <bundle.mcpb> <tag>

bundle-name prints the file name the entry points at, or nothing for an
entry without a bundle. fill refuses a bundle whose file name is not that
one, an entry that points at another release than the tag, and an entry
that no longer holds the placeholder, so a hash is never written twice or
for the wrong file.

The registry takes an entry whole or not at all. Should it refuse the one
with the bundle, the action drops the bundle and publishes the rest, so the
version is listed at least with its other packages:

    registry_entry.py drop <server.json>

Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PLACEHOLDER = "0" * 64


def _read(server_json: Path) -> dict[str, Any]:
    entry: dict[str, Any] = json.loads(server_json.read_text("utf-8"))
    return entry


def _write(server_json: Path, entry: dict[str, Any]) -> None:
    text = json.dumps(entry, indent=2, ensure_ascii=False) + "\n"
    server_json.write_text(text, "utf-8", newline="\n")


def _bundles(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in entry.get("packages", []) if p.get("registryType") == "mcpb"]


def bundle_name(server_json: Path) -> str:
    """The file name of the bundle the entry points at, or an empty string."""
    bundles = _bundles(_read(server_json))
    if not bundles:
        return ""
    if len(bundles) > 1:
        raise SystemExit("the entry lists more than one bundle")
    name: str = bundles[0]["identifier"].rsplit("/", 1)[-1]
    return name


def fill(server_json: Path, bundle: Path, tag: str) -> str:
    entry = _read(server_json)
    (package,) = _bundles(entry)
    named = package["identifier"]
    if named.rsplit("/", 1)[-1] != bundle.name:
        raise SystemExit(f"{bundle.name} is not the file the entry points at: {named}")
    # The registry downloads the bundle from this address. A file name that
    # fits under another release's tag would only show as a refusal.
    if not named.endswith(f"/releases/download/{tag}/{bundle.name}"):
        raise SystemExit(f"the entry points at another release than {tag}: {named}")
    if package["fileSha256"] != PLACEHOLDER:
        raise SystemExit("the entry's fileSha256 is not the placeholder")
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    package["fileSha256"] = digest
    _write(server_json, entry)
    return digest


def drop(server_json: Path) -> None:
    entry = _read(server_json)
    kept = [p for p in entry["packages"] if p.get("registryType") != "mcpb"]
    if len(kept) == len(entry["packages"]):
        raise SystemExit("the entry lists no bundle to drop")
    entry["packages"] = kept
    _write(server_json, entry)


USAGE = (
    "usage: registry_entry.py bundle-name <server.json>\n"
    "       registry_entry.py fill <server.json> <bundle.mcpb> <tag>\n"
    "       registry_entry.py drop <server.json>"
)


def main(argv: list[str]) -> int:
    match argv:
        case ["bundle-name", entry]:
            print(bundle_name(Path(entry)))
        case ["fill", entry, bundle, tag]:
            print(fill(Path(entry), Path(bundle), tag), file=sys.stderr)
        case ["drop", entry]:
            drop(Path(entry))
        case _:
            print(USAGE, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
