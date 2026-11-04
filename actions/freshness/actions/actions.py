"""GitHub Actions a repository pins by commit, checked against their releases.

Every ``uses:`` in a workflow or a composite action that names a commit of
forty hexadecimal digits is a pin. The comment beside it, ``# v7.0.1``, is
the version it stands for. A reference to a tag or a branch, a local path or
a container floats on purpose and is left out. The same commit in several
files is one finding, and an action in a folder of its repository shares the
releases of that repository.

The newest release of each repository is asked from the GitHub API, or the
newest version tag where a repository publishes no releases. Its tag is
resolved to a commit, through the tag object when the tag is annotated, and
compared with the pin. ROOT names the repository, FINDINGS the folder to
write, GH_TOKEN the token for the API. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

API = "https://api.github.com"
SKIPPED_FOLDERS = {".git", ".venv", "node_modules", "__pycache__"}
FILES = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "**/action.yml",
    "**/action.yaml",
)

_USES = re.compile(r"^\s*-?\s*uses:\s*[\"']?([^\"'\s#]+)[\"']?(?:\s*#\s*(\S+))?")
_PIN = re.compile(r"^([\w.-]+/[\w.-]+)(?:/[^@]*)?@([0-9a-f]{40})$")

Fetch = Callable[[str], tuple[int, bytes]]


@dataclass(frozen=True)
class Pin:
    repository: str
    commit: str
    version: str
    """The version in the comment beside the commit, or empty."""


def pins_in(text: str) -> list[Pin]:
    """Every pinned action in a workflow or an action file, as written."""
    found = []
    for line in text.splitlines():
        match = _USES.match(line)
        if not match:
            continue
        pin = _PIN.match(match[1])
        if pin:
            comment = match[2] or ""
            version = comment if re.match(r"v?\d", comment) else ""
            found.append(Pin(pin[1], pin[2], version))
    return found


def files_to_read(root: Path) -> list[Path]:
    found = {
        path
        for pattern in FILES
        for path in root.glob(pattern)
        if path.is_file() and not SKIPPED_FOLDERS & set(path.relative_to(root).parts)
    }
    return sorted(found)


def collect(root: Path, files: Iterable[Path]) -> dict[Pin, list[str]]:
    """Every pin and the files that hold it. The version comes from the first
    file that gives one."""
    where: dict[tuple[str, str], set[str]] = defaultdict(set)
    versions: dict[tuple[str, str], str] = {}
    for path in files:
        for pin in pins_in(path.read_text("utf-8", errors="replace")):
            key = (pin.repository, pin.commit)
            where[key].add(path.relative_to(root).as_posix())
            if not versions.get(key):
                versions[key] = pin.version
    return {
        Pin(repository, commit, versions[(repository, commit)]): sorted(files)
        for (repository, commit), files in where.items()
    }


def version_key(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", tag))


class Api:
    def __init__(self, fetch: Fetch) -> None:
        self._fetch = fetch

    def get(self, path: str) -> Any:
        """The JSON of an endpoint, None for 404."""
        status, body = self._fetch(f"{API}/{path}")
        if status == 404:
            return None
        if status != 200:
            raise LookupError(f"{API}/{path} answered {status}")
        return json.loads(body)

    def newest(self, repository: str) -> tuple[str, str] | None:
        """The newest release's tag and commit, or the newest version tag
        where there are no releases, or None where there is neither."""
        release = self.get(f"repos/{repository}/releases/latest")
        if release:
            tag: str = release["tag_name"]
            return tag, self.commit_of(repository, tag)
        tags = [
            t
            for t in self.get(f"repos/{repository}/tags?per_page=100") or []
            if re.match(r"v?\d", t["name"])
        ]
        if not tags:
            return None
        newest = max(tags, key=lambda t: version_key(t["name"]))
        return newest["name"], self.commit_of(repository, newest["name"])

    def commit_of(self, repository: str, tag: str) -> str:
        """The commit a tag names, through the tag object for an annotated tag."""
        ref = self.get(f"repos/{repository}/git/ref/tags/{tag}")
        if not ref:
            raise LookupError(f"{repository} has no tag {tag}")
        sha: str = ref["object"]["sha"]
        if ref["object"]["type"] == "tag":
            sha = self.get(f"repos/{repository}/git/tags/{sha}")["object"]["sha"]
        return sha


def check(pin: Pin, files: list[str], api: Api) -> dict[str, Any] | None:
    newest = api.newest(pin.repository)
    if newest is None:
        print(
            f"::warning::{pin.repository} has no release and no version tag to compare."
        )
        return None
    tag, commit = newest
    if commit == pin.commit:
        return None
    return {
        "category": "action",
        "name": pin.repository,
        "where": files,
        "current": pin.version or pin.commit[:12],
        "newest": tag,
    }


def fetch_url(url: str) -> tuple[int, bytes]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, b""


def write(folder: Path, findings: list[dict[str, Any]], checked: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(f, sort_keys=True) + "\n" for f in findings)
    (folder / "findings.jsonl").write_text(lines, "utf-8")
    status = {"result": "ok", "checked": checked}
    (folder / "status.json").write_text(json.dumps(status) + "\n", "utf-8")


def main() -> int:
    root = Path(os.environ.get("ROOT") or Path.cwd())
    api = Api(fetch_url)
    try:
        pins = collect(root, files_to_read(root))
        findings = []
        for pin, files in sorted(
            pins.items(), key=lambda p: (p[0].repository, p[0].commit)
        ):
            finding = check(pin, files, api)
            if finding:
                findings.append(finding)
    except (OSError, ValueError, LookupError, KeyError, urllib.error.URLError) as error:
        print(f"::error::Could not check the actions: {error}", file=sys.stderr)
        return 1
    write(Path(os.environ["FINDINGS"]), findings, len(pins))
    print(f"{len(pins)} pinned actions checked, {len(findings)} findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
