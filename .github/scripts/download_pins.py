"""Report pinned downloads with a newer release or a checksum that is not official.

Every entry of download-pins.yml names a file that pins a download by
version and SHA-256, and the GitHub repository whose releases it comes from.
For each, this compares the pin with the newest release and the pinned
checksum with the one in the checksums file of the pinned release. It prints
a Markdown report for the issue, or nothing when every pin is current.

CONFIG names the list (default .github/download-pins.yml), GH_TOKEN is used
for the GitHub API, GITHUB_SERVER_URL and GITHUB_REPOSITORY build the links.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

Fetch = Callable[[str], bytes]
API = "https://api.github.com"


@dataclass(frozen=True)
class Pin:
    name: str
    file: str
    version: str
    sha256: str
    repository: str
    asset: str
    checksums: str


def load(config: Path) -> list[Pin]:
    """The entries of ``config``, or ValueError naming what is wrong with one."""
    entries = yaml.safe_load(config.read_text("utf-8")) or []
    if not isinstance(entries, list):
        raise ValueError(f"{config} is not a list of entries")
    fields = set(Pin.__dataclass_fields__)
    pins = []
    for number, entry in enumerate(entries, 1):
        keys = set(entry) if isinstance(entry, dict) else set()
        if keys != fields or not all(
            isinstance(entry[k], str) and entry[k] for k in keys
        ):
            missing = ", ".join(sorted(fields - keys)) or "none"
            unknown = ", ".join(sorted(keys - fields)) or "none"
            raise ValueError(
                f"entry {number} of {config} needs exactly these keys, each with "
                f"a text: {', '.join(sorted(fields))}. Missing: {missing}. "
                f"Unknown: {unknown}."
            )
        pins.append(Pin(**entry))
    return pins


def fetch_url(url: str) -> bytes:
    """GET ``url``. The token goes to the API only, not to a download host."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN", "")
    if url.startswith(API) and token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        body: bytes = response.read()
        return body


def pinned_value(text: str, key: str) -> str:
    """The value of ``key:`` in a YAML file, without quotes or a comment."""
    match = re.search(rf"^\s*{re.escape(key)}:\s*[\"']?([^\"'\s#]+)", text, re.M)
    return match.group(1) if match else ""


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def _release(fetch: Fetch, repository: str, which: str) -> dict[str, Any]:
    release: dict[str, Any] = json.loads(
        fetch(f"{API}/repos/{repository}/releases/{which}")
    )
    return release


def _checksum(fetch: Fetch, release: dict[str, Any], pin: Pin) -> tuple[str, str]:
    """The official SHA-256 of the asset in ``release``, and the URL of the file
    that lists it."""
    urls = [
        a["browser_download_url"]
        for a in release.get("assets", [])
        if a["name"].endswith(pin.checksums)
    ]
    if len(urls) != 1:
        raise LookupError(
            f"{release['tag_name']} has no single file ending in {pin.checksums}"
        )
    for line in fetch(urls[0]).decode("utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == pin.asset:
            return parts[0], urls[0]
    raise LookupError(f"{urls[0]} lists no {pin.asset}")


def check(pin: Pin, root: Path, fetch: Fetch, base: str) -> str:
    """The section of the report for ``pin``, or an empty string."""
    link = f"[{pin.file}]({base}/blob/main/{pin.file})"
    text = (root / pin.file).read_text("utf-8")
    version, sha = pinned_value(text, pin.version), pinned_value(text, pin.sha256)
    if not version or not sha:
        return f"### {pin.name}\n\n{link} has no {pin.version} or no {pin.sha256}.\n"

    official, official_sums = _checksum(
        fetch, _release(fetch, pin.repository, f"tags/{version}"), pin
    )
    latest = _release(fetch, pin.repository, "latest")
    lines: list[str] = []
    if version_key(latest["tag_name"]) > version_key(version):
        new_sha, new_sums = _checksum(fetch, latest, pin)
        lines += [
            f"{link} pins {version}. "
            f"[{latest['tag_name']}]({latest['html_url']}) is out. "
            "To update, set these two lines there:",
            "",
            "```yaml",
            f"{pin.version}: {latest['tag_name']}",
            f"{pin.sha256}: {new_sha}",
            "```",
            "",
            f"The checksum is the line for `{pin.asset}` in the release's "
            f"[checksums file]({new_sums}).",
        ]
    elif sha != official:
        lines += [
            f"{link} pins {version} with a checksum that is not the one in the "
            f"[checksums file]({official_sums}) of that release. The official one is:",
            "",
            "```yaml",
            f"{pin.sha256}: {official}",
            "```",
        ]
    if not lines:
        return ""
    return "\n".join([f"### {pin.name}", "", *lines]) + "\n"


def report(pins: list[Pin], root: Path, fetch: Fetch, base: str) -> str:
    sections = [s for s in (check(pin, root, fetch, base) for pin in pins) if s]
    if not sections:
        return ""
    return "\n".join(["These pinned downloads need an update:", "", *sections])


def main() -> int:
    root = Path.cwd()
    config = root / (os.environ.get("CONFIG") or ".github/download-pins.yml")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    base = f"{server}/{os.environ.get('GITHUB_REPOSITORY', '')}"
    try:
        print(report(load(config), root, fetch_url, base), end="")
    except (urllib.error.URLError, LookupError, ValueError) as error:
        print(
            f"::error::Could not check the pinned downloads: {error}", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
