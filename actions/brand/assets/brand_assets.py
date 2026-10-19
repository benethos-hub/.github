"""The brand rules of the organisation, and the two places that apply them.

Every repository carries in assets/brand:

    icon.svg            the icon, the source of the other two
    icon.png            exported from it, 512x512
    social-preview.png  exported from it, 1280x640

Neither PNG may be older than the last change to the SVG: the last commit
that changed it is the same as or later than the last commit that changed
the SVG. The rules are written once, in problems(), and applied twice:

    brand_assets.py check
        In a checkout, as the CI check of a repository does. Files come from
        the working tree, their order from git. Prints ::error lines.

    brand_assets.py report
        Over every public repository of ORG through the GitHub API, as the
        weekly report does. Also compares the social preview uploaded in the
        repository settings with the file. Prints the Markdown for the issue,
        or nothing when every repository meets the rules.

GH_TOKEN is used for the GitHub API. Standard library only, since the check
runs in other repositories without an environment of its own.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

SVG = "assets/brand/icon.svg"
PNGS = {
    "assets/brand/icon.png": (512, 512),
    "assets/brand/social-preview.png": (1280, 640),
}
PREVIEW = "assets/brand/social-preview.png"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
API = "https://api.github.com"

Read = Callable[[str], bytes | None]
Current = Callable[[str], bool]


@dataclass(frozen=True)
class Problem:
    """A rule ``path`` breaks. ``other`` is a second path the text ends with."""

    path: str
    text: str
    other: str = ""

    def describe(self, name: Callable[[str], str] = str) -> str:
        """The problem in words, each path passed through ``name``, which the
        report uses to set paths as code."""
        words = [name(self.path), self.text]
        if self.other:
            words.append(name(self.other))
        return " ".join(words)


def png_size(data: bytes) -> tuple[int, int] | None:
    """Width and height of a PNG, the two numbers at offset 16, or None for a
    file that is no PNG."""
    if not data.startswith(PNG_SIGNATURE) or len(data) < 24:
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def problems(read: Read, current: Current) -> list[Problem]:
    """Every rule the assets of one repository break. ``read`` returns a
    file's content or None when it is missing or empty. ``current`` says
    whether a PNG is not older than the last change to the SVG."""
    found = []
    svg = read(SVG)
    if svg is None:
        found.append(Problem(SVG, "is missing"))
    elif b"<svg" not in svg:
        found.append(Problem(SVG, "is not an SVG file"))
    for path, (width, height) in PNGS.items():
        data = read(path)
        if data is None:
            found.append(Problem(path, "is missing"))
            continue
        size = png_size(data)
        if size is None:
            found.append(Problem(path, "is not a PNG file"))
            continue
        if size != (width, height):
            found.append(
                Problem(
                    path, f"is {size[0]}x{size[1]} pixels instead of {width}x{height}"
                )
            )
        if svg is not None and not current(path):
            found.append(Problem(path, "is older than the last change to", SVG))
    return found


# The CI check, in a checkout.


def _git_last_commit(path: str) -> str:
    done = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _read_local(path: str) -> bytes | None:
    try:
        data = open(path, "rb").read()
    except FileNotFoundError:
        return None
    return data or None


def _current_local(path: str) -> bool:
    ancestor = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            _git_last_commit(SVG),
            _git_last_commit(path),
        ],
        check=False,
    )
    return ancestor.returncode == 0


def check_local() -> int:
    found = problems(_read_local, _current_local)
    for problem in found:
        print(f"::error file={problem.path}::{problem.describe()}.")
    if found:
        print(
            "Every repository of benethos-hub needs assets/brand/icon.svg and, "
            "exported from it, a 512x512 icon.png and a 1280x640 social-preview.png."
        )
        return 1
    print("All brand assets are present and current.")
    return 0


# The report, over the GitHub API.


class GitHub:
    """The few calls the report needs. Tests replace it with canned answers."""

    def __init__(self, token: str) -> None:
        self.token = token

    def _open(self, request: urllib.request.Request) -> bytes:
        if request.full_url.startswith(API) and self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(request, timeout=30) as response:
            body: bytes = response.read()
            return body

    def get(self, url: str, accept: str = "application/vnd.github+json") -> bytes:
        return self._open(urllib.request.Request(url, headers={"Accept": accept}))

    def json(self, url: str) -> Any:
        return json.loads(self.get(url))

    def graphql(self, query: str, variables: dict[str, str]) -> Any:
        payload = json.dumps({"query": query, "variables": variables}).encode()
        request = urllib.request.Request(f"{API}/graphql", data=payload, method="POST")
        return json.loads(self._open(request))["data"]


PREVIEW_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    usesCustomOpenGraphImage
    openGraphImageUrl
  }
}
"""


def repositories(github: GitHub, org: str) -> list[str]:
    """The public repositories of ``org``, without archives, forks and .github."""
    names: list[str] = []
    page = 1
    while True:
        batch = github.json(
            f"{API}/orgs/{org}/repos?type=public&per_page=100&page={page}"
        )
        if not batch:
            return sorted(names)
        names += [
            r["name"]
            for r in batch
            if not r["archived"] and not r["fork"] and r["name"] != ".github"
        ]
        page += 1


def remote_problems(github: GitHub, org: str, repo: str) -> list[str]:
    """The report's lines for one repository, as Markdown."""
    base = f"{API}/repos/{org}/{repo}"
    files: dict[str, bytes | None] = {}

    def read(path: str) -> bytes | None:
        if path not in files:
            try:
                data = github.get(
                    f"{base}/contents/{path}", "application/vnd.github.raw"
                )
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                data = b""
            files[path] = data or None
        return files[path]

    commits: dict[str, str] = {}

    def last_commit(path: str) -> str:
        if path not in commits:
            url = f"{base}/commits?path={path}&per_page=1"
            commits[path] = github.json(url)[0]["sha"]
        return commits[path]

    def current(path: str) -> bool:
        compare = github.json(
            f"{base}/compare/{last_commit(SVG)}...{last_commit(path)}"
        )
        return compare["status"] in ("identical", "ahead")

    lines = [p.describe(lambda path: f"`{path}`") for p in problems(read, current)]

    # GitHub does not read the social preview from the repository. It has to
    # be uploaded in the settings, and GitHub keeps the upload byte for byte.
    preview = read(PREVIEW)
    if preview is not None:
        og = github.graphql(PREVIEW_QUERY, {"owner": org, "name": repo})["repository"]
        if not og["usesCustomOpenGraphImage"]:
            lines.append("no social preview is uploaded in the repository settings")
        elif github.get(og["openGraphImageUrl"], "*/*") != preview:
            lines.append(
                "the social preview uploaded in the repository settings "
                f"differs from `{PREVIEW}`"
            )
    return lines


def report(github: GitHub, org: str) -> str:
    sections = []
    for repo in repositories(github, org):
        lines = remote_problems(github, org, repo)
        if lines:
            sections.append(f"- [{repo}](https://github.com/{org}/{repo})")
            sections += [f"  - {line}" for line in lines]
    if not sections:
        return ""
    return "\n".join(
        [
            "These repositories do not meet the brand rules:",
            "",
            *sections,
            "",
            f"Every repository of the organisation needs its icon as `{SVG}` and, "
            "exported from it, a 512x512 `assets/brand/icon.png` and a 1280x640 "
            f"`{PREVIEW}`. Neither PNG may be older than the last change to the SVG. "
            "The social preview uploaded in the repository settings must be the "
            f"same file as `{PREVIEW}`.",
        ]
    )


def main(argv: list[str]) -> int:
    match argv:
        case ["check"]:
            return check_local()
        case ["report"]:
            try:
                github = GitHub(os.environ.get("GH_TOKEN", ""))
                print(report(github, os.environ["ORG"]), end="")
            except urllib.error.URLError as error:
                print(
                    f"::error::Could not check the brand assets: {error}",
                    file=sys.stderr,
                )
                return 1
            return 0
    print("usage: brand_assets.py check | report", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
