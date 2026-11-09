"""The report on pinned downloads, against canned GitHub releases.

The fetch stand-in serves release JSON and checksums files by URL, so the
report runs without the network. The last tests hold the real list to the
files it names.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".github" / "download-pins.yml"
WORKFLOW = yaml.safe_load(
    (ROOT / ".github" / "workflows" / "download-pins-report.yml").read_text("utf-8")
)

_spec = importlib.util.spec_from_file_location(
    "download_pins", ROOT / ".github" / "scripts" / "download_pins.py"
)
assert _spec and _spec.loader
download_pins = importlib.util.module_from_spec(_spec)
# A dataclass looks its module up in sys.modules while it is being defined.
sys.modules["download_pins"] = download_pins
_spec.loader.exec_module(download_pins)

API = "https://api.github.com/repos/example/tool/releases"
BASE = "https://github.com/benethos-hub/.github"
SHA = {"v1.9.0": "a" * 64, "v1.10.0": "b" * 64}


def _pin(**overrides: str) -> object:
    fields = {
        "name": "tool",
        "file": "action.yml",
        "version": "TOOL_VERSION",
        "sha256": "TOOL_SHA256",
        "repository": "example/tool",
        "asset": "tool_linux_amd64.tar.gz",
        "checksums": "_checksums.txt",
    } | overrides
    return download_pins.Pin(**fields)


def _pinned(tmp_path: Path, version: str = "v1.9.0", sha: str = SHA["v1.9.0"]) -> Path:
    (tmp_path / "action.yml").write_text(
        f"env:\n  TOOL_VERSION: {version}\n  TOOL_SHA256: {sha}  # pinned\n", "utf-8"
    )
    return tmp_path


def _fetch(latest: str = "v1.9.0"):
    def release(tag: str) -> bytes:
        return json.dumps(
            {
                "tag_name": tag,
                "html_url": f"https://github.com/example/tool/releases/tag/{tag}",
                "assets": [
                    {
                        "name": "tool_linux_amd64.tar.gz",
                        "browser_download_url": "unused",
                    },
                    {
                        "name": f"tool_{tag}_checksums.txt",
                        "browser_download_url": f"sums/{tag}",
                    },
                ],
            }
        ).encode()

    def fetch(url: str) -> bytes:
        if url == f"{API}/latest":
            return release(latest)
        if url.startswith(f"{API}/tags/"):
            return release(url.rsplit("/", 1)[1])
        if url.startswith("sums/"):
            tag = url.split("/", 1)[1]
            other = f"{'c' * 64}  other.tar.gz"
            ours = f"{SHA[tag]}  tool_linux_amd64.tar.gz"
            return f"{other}\n{ours}\n".encode()
        raise AssertionError(url)

    return fetch


def test_a_current_pin_is_not_reported(tmp_path):
    assert download_pins.report([_pin()], _pinned(tmp_path), _fetch(), BASE) == ""


def test_a_newer_release_comes_with_the_lines_to_paste(tmp_path):
    body = download_pins.report(
        [_pin()], _pinned(tmp_path), _fetch(latest="v1.10.0"), BASE
    )
    assert body.startswith("These pinned downloads need an update:\n\n### tool\n")
    assert f"[action.yml]({BASE}/blob/main/action.yml) pins v1.9.0." in body
    assert f"TOOL_VERSION: v1.10.0\nTOOL_SHA256: {SHA['v1.10.0']}\n" in body
    assert "[checksums file](sums/v1.10.0)" in body


def test_a_checksum_that_is_not_the_official_one_is_reported(tmp_path):
    body = download_pins.report(
        [_pin()], _pinned(tmp_path, sha="d" * 64), _fetch(), BASE
    )
    assert (
        "with a checksum that is not the one in the [checksums file](sums/v1.9.0)"
        in body
    )
    assert f"TOOL_SHA256: {SHA['v1.9.0']}" in body


def test_a_file_without_the_keys_is_reported(tmp_path):
    (tmp_path / "action.yml").write_text("env: {}\n", "utf-8")
    body = download_pins.report([_pin()], tmp_path, _fetch(), BASE)
    assert "has no TOOL_VERSION or no TOOL_SHA256" in body


def test_versions_compare_by_number_not_by_text():
    assert download_pins.version_key("v1.10.0") > download_pins.version_key("v1.9.0")
    assert download_pins.version_key("v2.0.0") > download_pins.version_key("v1.99.9")


def test_a_release_without_the_asset_is_an_error(tmp_path):
    with pytest.raises(LookupError, match="lists no tool_linux_arm64.tar.gz"):
        download_pins.report(
            [_pin(asset="tool_linux_arm64.tar.gz")], _pinned(tmp_path), _fetch(), BASE
        )


def test_a_version_in_the_asset_name_follows_the_release(tmp_path):
    pin = _pin(asset="tool_{version}_linux_amd64.tar.gz")
    assert download_pins.asset_name(pin, "v1.10.0") == "tool_1.10.0_linux_amd64.tar.gz"

    def fetch(url: str) -> bytes:
        if url.startswith("sums/"):
            tag = url.split("/", 1)[1]
            return f"{SHA[tag]}  tool_{tag[1:]}_linux_amd64.tar.gz\n".encode()
        return _fetch(latest="v1.10.0")(url)

    body = download_pins.report([pin], _pinned(tmp_path), fetch, BASE)
    assert f"TOOL_SHA256: {SHA['v1.10.0']}" in body
    assert "line for `tool_1.10.0_linux_amd64.tar.gz`" in body


def test_the_token_goes_to_the_api_only(monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"{}"

    def urlopen(request, timeout):
        seen.append((request.full_url, request.get_header("Authorization")))
        return Response()

    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setattr(download_pins.urllib.request, "urlopen", urlopen)
    download_pins.fetch_url("https://api.github.com/repos/example/tool/releases/latest")
    download_pins.fetch_url(
        "https://github.com/example/tool/releases/download/v1/sums.txt"
    )
    assert seen == [
        ("https://api.github.com/repos/example/tool/releases/latest", "Bearer secret"),
        ("https://github.com/example/tool/releases/download/v1/sums.txt", None),
    ]


def _refuse(final_url: str, body: bytes):
    def urlopen(request, timeout):
        raise download_pins.urllib.error.HTTPError(
            final_url, 403, "Forbidden", {}, io.BytesIO(body)
        )

    return urlopen


def test_a_refused_api_call_names_its_url_and_the_message(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "secret")
    body = json.dumps({"message": "API rate limit\n exceeded", "url": "x"}).encode()
    url = "https://api.github.com/repos/example/tool/releases/latest"
    monkeypatch.setattr(download_pins.urllib.request, "urlopen", _refuse(url, body))
    with pytest.raises(LookupError) as raised:
        download_pins.fetch_url(url)
    assert str(raised.value) == f"{url} answered 403: API rate limit exceeded"
    assert "secret" not in str(raised.value)


def test_a_refused_download_names_only_the_host_of_its_redirect(monkeypatch):
    """The redirect goes to a signed URL, and the body may echo it."""
    signed = "https://assets.example.net/x/sums.txt?sig=SIGNED&expires=1"
    body = b"<Error>sig=SIGNED</Error>"
    url = "https://github.com/example/tool/releases/download/v1/sums.txt"
    monkeypatch.setattr(download_pins.urllib.request, "urlopen", _refuse(signed, body))
    with pytest.raises(LookupError) as raised:
        download_pins.fetch_url(url)
    assert str(raised.value) == (
        f"{url} answered 403 after a redirect to assets.example.net"
    )


def test_a_refused_request_ends_the_script_with_its_url(tmp_path, monkeypatch, capsys):
    (tmp_path / "tool.yml").write_text("V: v1.0.0\nS: abc\n", "utf-8")
    (tmp_path / "pins.yml").write_text(
        "- {name: tool, file: tool.yml, version: V, sha256: S,"
        " repository: example/tool, asset: tool, checksums: sums.txt}\n",
        "utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG", "pins.yml")
    url = "https://api.github.com/repos/example/tool/releases/tags/v1.0.0"
    monkeypatch.setattr(download_pins.urllib.request, "urlopen", _refuse(url, b""))
    assert download_pins.main() == 1
    assert capsys.readouterr().err == (
        f"::error::Could not check the pinned downloads: {url} answered 403\n"
    )


# The real list.


def test_every_entry_names_a_file_that_pins_both_values():
    pins = download_pins.load(CONFIG)
    assert pins
    for pin in pins:
        text = (ROOT / pin.file).read_text("utf-8")
        assert download_pins.pinned_value(text, pin.version).startswith("v"), pin.name
        assert len(download_pins.pinned_value(text, pin.sha256)) == 64, pin.name


def test_the_workflow_runs_the_script_from_the_lockfile():
    steps = WORKFLOW["jobs"]["report"]["steps"]
    (check,) = [s for s in steps if s.get("name") == "Check every pin"]
    assert (
        check["run"]
        == 'uv run --frozen .github/scripts/download_pins.py > "$RUNNER_TEMP/report.md"'
    )


def test_the_workflow_keeps_its_issue_with_the_shared_action():
    issue = WORKFLOW["jobs"]["report"]["steps"][-1]
    assert issue["uses"] == "./actions/report-issue"
    assert issue["with"]["title"] == "Pinned downloads need an update"
    assert issue["with"]["report"] == "${{ runner.temp }}/report.md"


@pytest.mark.parametrize(
    ("entry", "named"),
    [
        (
            "- name: tool\n  file: action.yml\n",
            "Missing: asset, checksums, repository, sha256, version",
        ),
        (
            "- name: tool\n  file: action.yml\n  version: V\n  sha256: S\n"
            "  repository: r/t\n  asset: a\n  checksums: c\n  checksum: typo\n",
            "Unknown: checksum.",
        ),
        ("- just a text\n", "Missing: asset, checksums, file, name"),
    ],
)
def test_a_broken_entry_is_named_without_a_traceback(
    tmp_path, monkeypatch, capsys, entry, named
):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "download-pins.yml").write_text(entry, "utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONFIG", raising=False)
    assert download_pins.main() == 1
    err = capsys.readouterr().err
    assert err.startswith("::error::Could not check the pinned downloads: entry 1 of ")
    assert named in err
