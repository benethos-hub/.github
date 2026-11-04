"""The image check of the freshness workflow, against a stand-in registry:
which references count, when a moved digest is a rebuild, and which tag of
the same form is the newest.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "actions" / "freshness" / "images"
ACTION = yaml.safe_load((FOLDER / "action.yml").read_text("utf-8"))

_spec = importlib.util.spec_from_file_location("freshness_images", FOLDER / "images.py")
assert _spec and _spec.loader
images = importlib.util.module_from_spec(_spec)
sys.modules["freshness_images"] = images
_spec.loader.exec_module(images)

OLD = "sha256:" + "a" * 64
NEW = "sha256:" + "b" * 64
AMD64_OLD, AMD64_NEW = "sha256:" + "1" * 64, "sha256:" + "2" * 64
ARM64 = "sha256:" + "3" * 64
RISCV_OLD, RISCV_NEW = "sha256:" + "4" * 64, "sha256:" + "5" * 64

DOCKERFILE = f"""\
FROM ghcr.io/example/tool:0.13.7@{OLD} AS tool
FROM --platform=$BUILDPLATFORM python:3.15-slim@{OLD} AS builder
RUN echo build
FROM python:3.15-slim@{OLD}
COPY --from=tool /tool /usr/bin/tool
FROM builder AS tests
FROM scratch
"""

COMPOSE = """\
services:
  app:
    image: ghcr.io/example/app:${APP_VERSION:?set APP_VERSION in .env}
  dev:
    image: example-app:local
  proxy:
    image: caddy:2
  mail:
    image: "example/server:v0.16"
"""


def _index(amd64: str, riscv: str) -> dict[str, object]:
    return {
        "manifests": [
            {"digest": amd64, "platform": {"os": "linux", "architecture": "amd64"}},
            {"digest": ARM64, "platform": {"os": "linux", "architecture": "arm64"}},
            {
                "digest": "sha256:" + "6" * 64,
                "platform": {"os": "linux", "architecture": "arm", "variant": "v7"},
            },
            {"digest": riscv, "platform": {"os": "linux", "architecture": "riscv64"}},
            {
                "digest": "sha256:" + "7" * 64,
                "platform": {"os": "unknown", "architecture": "unknown"},
            },
        ]
    }


class FakeRegistry:
    """Answers manifests and tag lists by URL, and asks for a token first."""

    def __init__(
        self, manifests: dict[str, tuple[str, dict[str, object]]], tags: list[str]
    ):
        self.manifests = manifests
        self.tags = tags
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]) -> images.Response:
        self.calls.append(url)
        if url.startswith("https://auth.example/token"):
            return images.Response(200, {}, json.dumps({"token": "t0k3n"}).encode())
        if "Authorization" not in headers:
            challenge = 'Bearer realm="https://auth.example/token",service="registry",scope="pull"'
            return images.Response(401, {"WWW-Authenticate": challenge}, b"")
        assert headers["Authorization"] == "Bearer t0k3n"
        if "/manifests/" in url:
            which = url.rsplit("/manifests/", 1)[1]
            if which not in self.manifests:
                return images.Response(404, {}, b"")
            digest, body = self.manifests[which]
            return images.Response(
                200, {"Docker-Content-Digest": digest}, json.dumps(body).encode()
            )
        if "/tags/list" in url:
            page = self.tags[:2]
            rest = self.tags[2:]
            headers_out = {}
            if rest and "last=" not in url:
                headers_out["Link"] = (
                    f"</v2/{url.split('/v2/')[1].split('/tags/')[0]}/tags/list"
                    f'?n=2&last={page[-1]}>; rel="next"'
                )
            if "last=" in url:
                page = rest
            return images.Response(
                200, headers_out, json.dumps({"name": "x", "tags": page}).encode()
            )
        raise AssertionError(url)


def _registry(manifests=None, tags=()):
    fake = FakeRegistry(manifests or {}, list(tags))
    return images.Registry(images._lower_headers(fake)), fake


def _ref(text: str) -> images.Reference:
    reference = images.parse_reference(text)
    assert reference
    return reference


# --- references ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "registry", "repository", "tag", "digest", "name"),
    [
        ("python:3.15-slim", "docker.io", "library/python", "3.15-slim", "", "python"),
        (
            f"python:3.15-slim@{OLD}",
            "docker.io",
            "library/python",
            "3.15-slim",
            OLD,
            "python",
        ),
        (
            "example/server:v0.16",
            "docker.io",
            "example/server",
            "v0.16",
            "",
            "example/server",
        ),
        (
            "ghcr.io/example/tool:0.13.7",
            "ghcr.io",
            "example/tool",
            "0.13.7",
            "",
            "ghcr.io/example/tool",
        ),
        (
            "localhost:5000/app:1",
            "localhost:5000",
            "app",
            "1",
            "",
            "localhost:5000/app",
        ),
        ("caddy", "docker.io", "library/caddy", "", "", "caddy"),
    ],
)
def test_a_reference_is_taken_apart(text, registry, repository, tag, digest, name):
    reference = _ref(text)
    assert (reference.registry, reference.repository) == (registry, repository)
    assert (reference.tag, reference.digest, reference.name) == (tag, digest, name)


@pytest.mark.parametrize(
    "text",
    [
        "ghcr.io/x/app:${VERSION:?set it}",
        "${{ matrix.image }}",
        "scratch",
        "Not An Image",
    ],
)
def test_a_reference_that_floats_is_none(text):
    assert images.parse_reference(text) is None


def test_a_dockerfile_gives_every_base_but_its_own_stages(tmp_path):
    path = tmp_path / "Dockerfile"
    assert images.references_in(path, DOCKERFILE) == [
        f"ghcr.io/example/tool:0.13.7@{OLD}",
        f"python:3.15-slim@{OLD}",
        f"python:3.15-slim@{OLD}",
        "scratch",
    ]


def test_a_yaml_file_gives_every_image_line(tmp_path):
    assert images.references_in(tmp_path / "compose.yaml", COMPOSE) == [
        "ghcr.io/example/app:${APP_VERSION:?set APP_VERSION in .env}",
        "example-app:local",
        "caddy:2",
        "example/server:v0.16",
    ]


def test_the_same_pin_in_two_files_is_one_reference_and_floating_ones_are_left_out(
    tmp_path,
):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "Dockerfile").write_text(DOCKERFILE, "utf-8")
    (tmp_path / "b" / "Dockerfile").write_text(DOCKERFILE, "utf-8")
    (tmp_path / "compose.yaml").write_text(COMPOSE, "utf-8")
    pins = images.collect(tmp_path, images.files_to_read(tmp_path, []))
    assert {r.pinned: files for r, files in pins.items()} == {
        "ghcr.io/example/tool:0.13.7": ["a/Dockerfile", "b/Dockerfile"],
        "python:3.15-slim": ["a/Dockerfile", "b/Dockerfile"],
        "caddy:2": ["compose.yaml"],
        "example/server:v0.16": ["compose.yaml"],
    }


def test_the_default_files_leave_the_workflows_out_and_patterns_replace_them(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "publish.yml").write_text(
        "image: x:1\n", "utf-8"
    )
    (tmp_path / "containers").mkdir()
    (tmp_path / "containers" / "mcp.yaml").write_text("image: y:1\n", "utf-8")
    (tmp_path / "containers" / "Dockerfile.dev").write_text("FROM z:1\n", "utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "Dockerfile").write_text("FROM n:1\n", "utf-8")
    default = images.files_to_read(tmp_path, [])
    assert [p.relative_to(tmp_path).as_posix() for p in default] == [
        "containers/Dockerfile.dev",
        "containers/mcp.yaml",
    ]
    chosen = images.files_to_read(tmp_path, ["containers/*.yaml"])
    assert [p.relative_to(tmp_path).as_posix() for p in chosen] == [
        "containers/mcp.yaml"
    ]


# --- the digest -----------------------------------------------------------------


PLATFORMS = ["linux/amd64", "linux/arm64"]


def _digest_findings(now_index, tags=("3.15-slim",)):
    registry, fake = _registry(
        {"3.15-slim": (NEW, now_index), OLD: (OLD, _index(AMD64_OLD, RISCV_OLD))}, tags
    )
    reference = _ref(f"python:3.15-slim@{OLD}")
    return images.check(reference, ["Dockerfile"], registry, PLATFORMS), fake


def test_a_rebuild_of_a_foreign_platform_is_no_finding():
    findings, _ = _digest_findings(_index(AMD64_OLD, RISCV_NEW))
    assert findings == []


def test_a_rebuild_of_a_wanted_platform_is_a_finding():
    findings, _ = _digest_findings(_index(AMD64_NEW, RISCV_OLD))
    assert findings == [
        {
            "category": "image",
            "name": "python:3.15-slim",
            "where": ["Dockerfile"],
            "current": OLD[:19],
            "newest": NEW[:19],
            "kind": "rebuild",
        }
    ]


def test_an_unchanged_digest_asks_nothing_more():
    registry, fake = _registry(
        {"3.15-slim": (OLD, _index(AMD64_OLD, RISCV_OLD))}, ["3.15-slim"]
    )
    assert (
        images.check(_ref(f"python:3.15-slim@{OLD}"), ["f"], registry, PLATFORMS) == []
    )
    assert not any(OLD in url for url in fake.calls)


def test_a_single_manifest_is_compared_by_its_config():
    registry, _ = _registry(
        {
            "1.0": (NEW, {"config": {"digest": "sha256:" + "9" * 64}}),
            OLD: (OLD, {"config": {"digest": "sha256:" + "8" * 64}}),
        },
        ["1.0"],
    )
    (finding,) = images.check(
        _ref(f"example/app:1.0@{OLD}"), ["f"], registry, PLATFORMS
    )
    assert finding["kind"] == "rebuild"


def test_a_platform_variant_is_matched_exactly():
    index = _index(AMD64_OLD, RISCV_OLD)
    digests = images.platform_digests(
        index, ["linux/arm/v7", "linux/arm/v6", "linux/amd64"]
    )
    assert digests == {"linux/arm/v7": "sha256:" + "6" * 64, "linux/amd64": AMD64_OLD}


def test_a_tag_that_is_gone_is_a_warning_and_no_finding(capsys):
    registry, _ = _registry({}, ["3.15-slim"])
    assert (
        images.check(_ref(f"python:3.15-slim@{OLD}"), ["f"], registry, PLATFORMS) == []
    )
    assert "::warning::python:3.15-slim is gone" in capsys.readouterr().out


# --- the tag --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "tags", "newest"),
    [
        (
            "3.15-slim",
            ["3.15-slim", "3.16-slim", "3.16-rc-slim", "3.16", "latest"],
            "3.16-slim",
        ),
        ("0.13.7", ["0.13.7", "0.13.8", "0.14.0", "0.14", "latest"], "0.14.0"),
        ("v0.16", ["v0.16", "v0.17", "v0.16.1", "0.18"], "v0.17"),
        ("2", ["2", "2.10", "1", "2-alpine"], "2"),
        ("2", ["3", "2"], "3"),
        ("1.0", [], "1.0"),
    ],
)
def test_the_newest_tag_of_the_same_form(tag, tags, newest):
    assert images.newest_of_form(tag, tags) == newest


def test_a_newer_tag_is_a_finding_and_a_floating_one_still_gets_it():
    registry, fake = _registry({}, ["2", "3", "2.10"])
    (finding,) = images.check(_ref("caddy:2"), ["compose.yaml"], registry, PLATFORMS)
    assert finding == {
        "category": "image",
        "name": "caddy",
        "where": ["compose.yaml"],
        "current": "2",
        "newest": "3",
    }
    assert not any("/manifests/" in url for url in fake.calls)


def test_the_tag_list_is_read_across_pages():
    registry, fake = _registry({}, ["v0.16", "v0.15", "v0.17", "v0.18"])
    (finding,) = images.check(_ref("example/server:v0.16"), ["f"], registry, PLATFORMS)
    assert finding["newest"] == "v0.18"
    assert sum("last=v0.15" in url for url in fake.calls) == 1


def test_the_registry_asks_for_the_token_once_per_repository():
    registry, fake = _registry({}, ["1", "2"])
    images.check(_ref("example/app:1"), ["f"], registry, PLATFORMS)
    images.check(_ref("example/app:1"), ["f"], registry, PLATFORMS)
    assert sum(url.startswith("https://auth.example/token") for url in fake.calls) == 1
    assert fake.calls[0].startswith(
        "https://registry-1.docker.io/v2/example/app/tags/list"
    )


def test_a_registry_error_stops_the_check():
    def http(url: str, headers: dict[str, str]) -> images.Response:
        return images.Response(503, {}, b"")

    registry = images.Registry(http)
    with pytest.raises(LookupError):
        images.check(_ref("example/app:1"), ["f"], registry, PLATFORMS)


# --- the script -----------------------------------------------------------------


def test_the_script_writes_the_findings_and_the_status(tmp_path, monkeypatch):
    (tmp_path / "compose.yaml").write_text(
        "services:\n  a:\n    image: example-app:local\n", "utf-8"
    )
    run = subprocess.run(
        [sys.executable, str(FOLDER / "images.py")],
        env=os.environ | {"ROOT": str(tmp_path), "FINDINGS": str(tmp_path / "out")},
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "out" / "findings.jsonl").read_text("utf-8") == ""
    status = json.loads((tmp_path / "out" / "status.json").read_text("utf-8"))
    assert status == {"result": "ok", "checked": 0}
    assert "0 images checked, 0 findings." in run.stdout


# --- the action -----------------------------------------------------------------


def test_the_action_passes_the_files_the_platforms_and_the_folder():
    assert set(ACTION["inputs"]) == {"findings", "platforms", "files"}
    assert ACTION["inputs"]["platforms"]["default"] == "linux/amd64 linux/arm64"
    (run,) = [s for s in ACTION["runs"]["steps"] if "run" in s]
    assert '"$GITHUB_ACTION_PATH/images.py"' in run["run"]
    assert set(run["env"]) == {"FILES", "PLATFORMS", "FINDINGS"}
