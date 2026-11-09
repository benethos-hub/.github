"""Report pinned downloads with a newer release or a checksum that is not official.

Every entry of download-pins.yml names a file that pins a download by
version and SHA-256, and the GitHub repository whose releases it comes from.
For each, this compares the pin with the newest release and the pinned
checksum with the one in the checksums file of the pinned release. It prints
a Markdown report for the issue, or nothing when every pin is current.

Everything is read from github.com without a token, the way the actions
download the files themselves: the newest release from the redirect of
``releases/latest``, the checksums from ``releases/download``. The GitHub API
is not used, so an organisation with an IP allow list cannot refuse it.

CONFIG names the list (default .github/download-pins.yml), GITHUB_SERVER_URL
and GITHUB_REPOSITORY build the links to the pinning files.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

GITHUB = "https://github.com"


@dataclass(frozen=True)
class Pin:
    name: str
    file: str
    version: str
    sha256: str
    repository: str
    asset: str
    checksums: str


@dataclass(frozen=True)
class Web:
    """How the script reaches github.com: ``get`` reads a file, ``final``
    gives the URL a redirect ends on."""

    get: Callable[[str], bytes]
    final: Callable[[str], str]


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


def _open(url: str, method: str) -> tuple[bytes, str]:
    """The body and the final URL of ``url``, without any token."""
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body: bytes = response.read()
            final: str = response.url
            return body, final
    except urllib.error.HTTPError as error:
        raise LookupError(http_error(url, error)) from None


def fetch_url(url: str) -> bytes:
    return _open(url, "GET")[0]


def final_url(url: str) -> str:
    return _open(url, "HEAD")[1]


def http_error(url: str, error: urllib.error.HTTPError) -> str:
    """What a failed request names in the log: the URL asked for, the status,
    the host a redirect ended on and the message of a JSON answer. A download
    is redirected to a signed URL, so of that only the host is named, and a
    body that is not JSON is left out."""
    text = f"{url} answered {error.code}"
    host = urllib.parse.urlsplit(error.url or url).hostname
    if host and host != urllib.parse.urlsplit(url).hostname:
        text += f" after a redirect to {host}"
    try:
        message = json.loads(error.read()).get("message")
    except (ValueError, AttributeError, OSError):
        message = None
    if isinstance(message, str) and message:
        text += f": {' '.join(message.split())[:300]}"
    return text


def pinned_value(text: str, key: str) -> str:
    """The value of ``key:`` in a YAML file, without quotes or a comment."""
    match = re.search(rf"^\s*{re.escape(key)}:\s*[\"']?([^\"'\s#]+)", text, re.M)
    return match.group(1) if match else ""


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def with_version(name: str, tag: str) -> str:
    """``name`` for the release tagged ``tag``. {version} stands for the tag
    without its v."""
    return name.replace("{version}", tag.removeprefix("v"))


def asset_name(pin: Pin, tag: str) -> str:
    return with_version(pin.asset, tag)


def release_url(pin: Pin, tag: str) -> str:
    return f"{GITHUB}/{pin.repository}/releases/tag/{tag}"


def latest_tag(web: Web, pin: Pin) -> str:
    """The tag of the release its maintainers marked as the latest, from the
    redirect of ``releases/latest``."""
    url = f"{GITHUB}/{pin.repository}/releases/latest"
    final = web.final(url)
    prefix = f"{GITHUB}/{pin.repository}/releases/tag/"
    if not final.startswith(prefix) or final == prefix:
        raise LookupError(f"{url} leads to {final}, not to a release")
    return urllib.parse.unquote(final.removeprefix(prefix))


def _checksum(web: Web, pin: Pin, tag: str) -> tuple[str, str]:
    """The official SHA-256 of the asset in the release tagged ``tag``, and
    the URL of the file that lists it."""
    asset = asset_name(pin, tag)
    sums = with_version(pin.checksums, tag)
    url = f"{GITHUB}/{pin.repository}/releases/download/{tag}/{sums}"
    for line in web.get(url).decode("utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == asset:
            return parts[0], url
    raise LookupError(f"{url} lists no {asset}")


def check(pin: Pin, root: Path, web: Web, base: str) -> str:
    """The section of the report for ``pin``, or an empty string."""
    link = f"[{pin.file}]({base}/blob/main/{pin.file})"
    text = (root / pin.file).read_text("utf-8")
    version, sha = pinned_value(text, pin.version), pinned_value(text, pin.sha256)
    if not version or not sha:
        return f"### {pin.name}\n\n{link} has no {pin.version} or no {pin.sha256}.\n"

    official, official_sums = _checksum(web, pin, version)
    latest = latest_tag(web, pin)
    lines: list[str] = []
    if version_key(latest) > version_key(version):
        new_sha, new_sums = _checksum(web, pin, latest)
        lines += [
            f"{link} pins {version}. "
            f"[{latest}]({release_url(pin, latest)}) is out. "
            "To update, set these two lines there:",
            "",
            "```yaml",
            f"{pin.version}: {latest}",
            f"{pin.sha256}: {new_sha}",
            "```",
            "",
            f"The checksum is the line for `{asset_name(pin, latest)}` "
            "in the release's "
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


def report(pins: list[Pin], root: Path, web: Web, base: str) -> str:
    sections = [s for s in (check(pin, root, web, base) for pin in pins) if s]
    if not sections:
        return ""
    return "\n".join(["These pinned downloads need an update:", "", *sections])


def main() -> int:
    root = Path.cwd()
    config = root / (os.environ.get("CONFIG") or ".github/download-pins.yml")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    base = f"{server}/{os.environ.get('GITHUB_REPOSITORY', '')}"
    try:
        print(report(load(config), root, Web(fetch_url, final_url), base), end="")
    except (urllib.error.URLError, LookupError, ValueError) as error:
        print(
            f"::error::Could not check the pinned downloads: {error}", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
