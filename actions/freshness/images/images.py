"""Container images a repository pins, checked against their registry.

Every FROM of a Dockerfile and every image: of a YAML file is a reference,
``registry/repository:tag@sha256:digest`` with the registry, the tag or the
digest left out. The workflows count too: the container or a service of a
job is a pin like any other, while the name of an image a workflow builds
has no tag and floats. A reference with a variable, a stage name of the same
Dockerfile or no digits in its tag floats on purpose and is left out. The
rest gets up to two checks, as findings for the report action:

* With a digest: the digest the tag points to now. A difference counts as
  a rebuild only when the manifest of one of the platforms asked for has
  changed. The index of a multi-platform image moves when any platform is
  rebuilt, and a rebuild of a foreign architecture is nobody's news.
* With a tag: the newest tag of the same form, where the form keeps every
  character of the tag and replaces each run of digits. 3.15-slim is one
  form, v0.16 another. An image pinned to an exact version never changes its
  digest, so a new release would be invisible without this.

Registries are asked through the distribution API with an anonymous bearer
token, as docker pull does. ROOT names the repository, FILES the patterns of
the files to read (empty for the default), PLATFORMS the platforms a rebuild
counts for, FINDINGS the folder to write. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKIPPED_FOLDERS = {".git", ".venv", "node_modules", "__pycache__"}
DEFAULT_FILES = ("**/Dockerfile*", "**/*.yml", "**/*.yaml")
MANIFEST_TYPES = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)
PAGE = 1000

_FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.I)
_IMAGE = re.compile(r"^\s*-?\s*image:\s*[\"']?([^\"'#]+)")
_REFERENCE = re.compile(
    r"^(?:(?P<registry>[^/]+\.[^/]+|localhost(?::\d+)?)/)?"
    r"(?P<repository>[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*)"
    r"(?::(?P<tag>[\w][\w.-]*))?"
    r"(?:@(?P<digest>sha256:[0-9a-f]{64}))?$"
)


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


Http = Callable[[str, dict[str, str]], Response]


@dataclass(frozen=True)
class Reference:
    registry: str
    repository: str
    tag: str
    digest: str

    @property
    def name(self) -> str:
        """The reference as people write it, without the default registry."""
        if self.registry != "docker.io":
            return f"{self.registry}/{self.repository}"
        return self.repository.removeprefix("library/")

    @property
    def pinned(self) -> str:
        return f"{self.name}:{self.tag}" if self.tag else self.name


def parse_reference(text: str) -> Reference | None:
    """The parts of a reference, or None for one that floats on purpose."""
    if "$" in text or "{" in text or text == "scratch":
        return None
    match = _REFERENCE.match(text)
    if not match:
        return None
    registry = match["registry"] or "docker.io"
    repository = match["repository"]
    if registry == "docker.io" and "/" not in repository:
        repository = f"library/{repository}"
    return Reference(registry, repository, match["tag"] or "", match["digest"] or "")


def references_in(path: Path, text: str) -> list[str]:
    """Every image reference in a Dockerfile or a YAML file, as written."""
    found: list[str] = []
    if path.name.lower().startswith("dockerfile"):
        stages: set[str] = set()
        for line in text.splitlines():
            match = _FROM.match(line)
            if not match:
                continue
            if match[1].lower() not in stages:
                found.append(match[1])
            if match[2]:
                stages.add(match[2].lower())
        return found
    return [m[1].strip() for line in text.splitlines() if (m := _IMAGE.match(line))]


def files_to_read(root: Path, patterns: Iterable[str]) -> list[Path]:
    found: set[Path] = set()
    for pattern in patterns or DEFAULT_FILES:
        for path in root.glob(pattern):
            if path.is_file() and not SKIPPED_FOLDERS & set(
                path.relative_to(root).parts
            ):
                found.add(path)
    return sorted(found)


def collect(root: Path, files: Iterable[Path]) -> dict[Reference, list[str]]:
    """Every pinned reference and the files that hold it."""
    where: dict[Reference, set[str]] = defaultdict(set)
    for path in files:
        for text in references_in(path, path.read_text("utf-8", errors="replace")):
            reference = parse_reference(text)
            if reference and (reference.digest or re.search(r"\d", reference.tag)):
                where[reference].add(path.relative_to(root).as_posix())
    return {r: sorted(f) for r, f in where.items()}


class Registry:
    """Anonymous reads from a registry, with the bearer token it asks for."""

    def __init__(self, http: Http) -> None:
        self._http = http
        self._tokens: dict[str, str] = {}

    def get(
        self, registry: str, path: str, accept: str = "application/json"
    ) -> Response:
        host = "registry-1.docker.io" if registry == "docker.io" else registry
        url = f"https://{host}/v2/{path}"
        headers = {"Accept": accept}
        key = f"{registry} {path.split('/manifests/')[0].split('/tags/')[0]}"
        if key in self._tokens:
            headers["Authorization"] = f"Bearer {self._tokens[key]}"
        response = self._http(url, headers)
        if response.status == 401 and key not in self._tokens:
            self._tokens[key] = self._token(
                response.headers.get("www-authenticate", "")
            )
            headers["Authorization"] = f"Bearer {self._tokens[key]}"
            response = self._http(url, headers)
        if response.status >= 400 and response.status != 404:
            raise LookupError(f"{url} answered {response.status}")
        return response

    def _token(self, challenge: str) -> str:
        fields = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
        if "realm" not in fields:
            raise LookupError(f"no bearer challenge in {challenge!r}")
        query = {k: v for k, v in fields.items() if k in ("service", "scope")}
        response = self._http(f"{fields['realm']}?{urllib.parse.urlencode(query)}", {})
        if response.status != 200:
            raise LookupError(f"{fields['realm']} answered {response.status}")
        data = json.loads(response.body)
        token: str = data.get("token") or data.get("access_token") or ""
        return token

    def manifest(
        self, reference: Reference, which: str
    ) -> tuple[str, dict[str, Any]] | None:
        """The digest and body of a tag or a digest, None when it is gone."""
        response = self.get(
            reference.registry,
            f"{reference.repository}/manifests/{which}",
            MANIFEST_TYPES,
        )
        if response.status == 404:
            return None
        digest = response.headers.get("docker-content-digest", "")
        body: dict[str, Any] = json.loads(response.body) if response.body else {}
        return digest, body

    def tags(self, reference: Reference) -> list[str]:
        tags: list[str] = []
        path: str | None = f"{reference.repository}/tags/list?n={PAGE}"
        while path:
            response = self.get(reference.registry, path)
            if response.status == 404:
                break
            tags += json.loads(response.body).get("tags") or []
            link = response.headers.get("link", "")
            match = re.search(r"<([^>]+)>;\s*rel=\"next\"", link)
            path = match[1].split("/v2/", 1)[-1] if match else None
        return tags


def platform_digests(body: dict[str, Any], platforms: Iterable[str]) -> dict[str, str]:
    """``platform -> manifest digest`` from an index, for the platforms asked
    for. A single manifest, which has no platforms, is itself for all."""
    wanted = list(platforms)
    if "manifests" not in body:
        return {p: body.get("config", {}).get("digest", "") for p in wanted}
    found = {}
    for entry in body["manifests"]:
        platform = entry.get("platform", {})
        parts = [platform.get("os", ""), platform.get("architecture", "")]
        if platform.get("variant"):
            parts.append(platform["variant"])
        for want in wanted:
            if want == "/".join(parts) or want == "/".join(parts[:2]):
                found[want] = entry["digest"]
    return found


def short(digest: str) -> str:
    return digest[:19] if digest.startswith("sha256:") else digest


def tag_form(tag: str) -> re.Pattern[str]:
    return re.compile("^" + re.sub(r"\d+", r"\\d+", re.escape(tag)) + "$")


def version_key(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", tag))


def newest_of_form(tag: str, tags: Iterable[str]) -> str:
    """The newest tag of the same form as ``tag``, ``tag`` itself at least."""
    form = tag_form(tag)
    return max((t for t in tags if form.match(t)), key=version_key, default=tag)


def check(
    reference: Reference, files: list[str], registry: Registry, platforms: list[str]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if reference.digest and reference.tag:
        now = registry.manifest(reference, reference.tag)
        if now is None:
            print(f"::warning::{reference.pinned} is gone from its registry.")
        elif now[0] != reference.digest:
            pinned = registry.manifest(reference, reference.digest)
            before = platform_digests(pinned[1], platforms) if pinned else {}
            after = platform_digests(now[1], platforms)
            if any(before.get(p) != after.get(p) for p in platforms if p in after):
                findings.append(
                    {
                        "category": "image",
                        "name": reference.pinned,
                        "where": files,
                        "current": short(reference.digest),
                        "newest": short(now[0]),
                        "kind": "rebuild",
                    }
                )
    if reference.tag and re.search(r"\d", reference.tag):
        newest = newest_of_form(reference.tag, registry.tags(reference))
        if newest != reference.tag:
            findings.append(
                {
                    "category": "image",
                    "name": reference.name,
                    "where": files,
                    "current": reference.tag,
                    "newest": newest,
                }
            )
    return findings


def http(url: str, headers: dict[str, str]) -> Response:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return Response(
                response.status, dict(response.headers.items()) | {}, response.read()
            )
    except urllib.error.HTTPError as error:
        return Response(
            error.code, {k.lower(): v for k, v in error.headers.items()}, b""
        )


def _lower_headers(http_: Http) -> Http:
    def call(url: str, headers: dict[str, str]) -> Response:
        response = http_(url, headers)
        return Response(
            response.status,
            {k.lower(): v for k, v in response.headers.items()},
            response.body,
        )

    return call


def write(folder: Path, findings: list[dict[str, Any]], checked: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(f, sort_keys=True) + "\n" for f in findings)
    (folder / "findings.jsonl").write_text(lines, "utf-8")
    status = {"result": "ok", "checked": checked}
    (folder / "status.json").write_text(json.dumps(status) + "\n", "utf-8")


def main() -> int:
    root = Path(os.environ.get("ROOT") or Path.cwd())
    patterns = os.environ.get("FILES", "").split()
    platforms = (
        os.environ.get("PLATFORMS", "linux/amd64 linux/arm64").replace(",", " ").split()
    )
    registry = Registry(_lower_headers(http))
    try:
        pins = collect(root, files_to_read(root, patterns))
        findings = []
        for reference, files in sorted(pins.items(), key=lambda p: p[0].pinned):
            findings += check(reference, files, registry, platforms)
    except (OSError, ValueError, LookupError, urllib.error.URLError) as error:
        print(f"::error::Could not check the images: {error}", file=sys.stderr)
        return 1
    write(Path(os.environ["FINDINGS"]), findings, len(pins))
    print(f"{len(pins)} images checked, {len(findings)} findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
