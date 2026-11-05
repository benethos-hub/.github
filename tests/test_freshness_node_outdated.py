"""The npm adapter of the freshness report: what counts as the newest version of
a package, which entries of a package-lock.json are findings, and what a run
that got no answer leaves behind.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "actions" / "node" / "freshness-outdated"
ACTION = yaml.safe_load((FOLDER / "action.yml").read_text("utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


outdated = _load("freshness_node_outdated", FOLDER / "npm_outdated.py")
report = _load(
    "freshness_report_for_npm",
    ROOT / "actions" / "freshness" / "report" / "report.py",
)


def _versions(*versions: str, **deprecated: str) -> dict[str, object]:
    """A registry answer. Keyword names stand for versions with _ for dots."""
    listed: dict[str, dict[str, object]] = {v: {"version": v} for v in versions}
    for version, message in deprecated.items():
        listed[version.replace("_", ".")] = {"deprecated": message}
    return {"name": "x", "dist-tags": {"latest": "0.0.1"}, "versions": listed}


def _registry(**answers: object):
    """A fetch that answers per package, by the part of the URL after the host.
    An int is a status, an exception is raised, anything else is the document."""
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, bytes]:
        calls.append(url)
        answer = answers[url.removeprefix(outdated.REGISTRY + "/")]
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, int):
            return answer, b""
        if isinstance(answer, bytes):
            return 200, answer
        return 200, json.dumps(answer).encode()

    return fetch, calls


def _entry(version: str, **fields: object) -> dict[str, object]:
    return {
        "version": version,
        "resolved": f"{outdated.REGISTRY}/x/-/x-{version}.tgz",
        "integrity": "sha512-x",
    } | fields


def _lock(*names: str, **packages: dict[str, object]) -> dict[str, dict[str, object]]:
    """A lockfile's packages, with names as direct dependencies of the root."""
    return {
        "": {"name": "example", "dependencies": dict.fromkeys(names, "*")},
    } | {f"node_modules/{name}": entry for name, entry in packages.items()}


def _run(packages, fetch):
    return outdated.measure(packages, "package-lock.json", fetch)


# --- the newest version -------------------------------------------------------


HTMX = _versions("2.0.11", "4.0.0-beta6", "4.0.0", "4.0.1")
HTMX["dist-tags"] = {"latest": "2.0.11", "next": "4.0.1"}


def test_a_pin_above_latest_finds_the_highest_stable_version_and_not_latest():
    """Measured on 2026-11-05: npm outdated says latest 2.0.11 for a pin at 4.0.0
    and never names 4.0.1."""
    fetch, _ = _registry(**{"htmx.org": HTMX})
    findings, _ = _run(_lock("htmx.org", **{"htmx.org": _entry("4.0.0")}), fetch)
    assert findings == [
        {
            "category": "package",
            "name": "htmx.org",
            "where": ["package-lock.json"],
            "current": "4.0.0",
            "newest": "4.0.1",
            "direct": True,
            "scope": "runtime",
        }
    ]


def test_a_pin_on_the_highest_stable_version_is_no_finding():
    fetch, _ = _registry(**{"htmx.org": HTMX})
    findings, status = _run(_lock("htmx.org", **{"htmx.org": _entry("4.0.1")}), fetch)
    assert findings == []
    assert status["result"] == "ok"
    assert status["checked"] == 1


def test_a_pre_release_above_the_locked_version_is_no_finding():
    fetch, _ = _registry(x=_versions("1.0.0", "1.1.0-beta.1", "2.0.0-rc.1"))
    findings, _ = _run(_lock("x", x=_entry("1.0.0")), fetch)
    assert findings == []


def test_a_deprecated_highest_version_gives_way_to_the_next_one():
    fetch, _ = _registry(x=_versions("1.0.0", "1.1.0", **{"1_2_0": "broken"}))
    findings, _ = _run(_lock("x", x=_entry("1.0.0")), fetch)
    assert [f["newest"] for f in findings] == ["1.1.0"]


def test_a_lock_on_a_deprecated_version_above_the_next_one_is_no_finding():
    fetch, _ = _registry(x=_versions("1.1.0", **{"1_2_0": "broken"}))
    findings, _ = _run(_lock("x", x=_entry("1.2.0")), fetch)
    assert findings == []


def test_every_version_deprecated_is_no_finding():
    fetch, _ = _registry(x=_versions(**{"1_0_0": "old", "1_1_0": "old"}))
    findings, _ = _run(_lock("x", x=_entry("1.0.0")), fetch)
    assert findings == []


def test_a_new_release_on_an_older_line_is_no_finding():
    fetch, _ = _registry(x=_versions("2.0.11", "2.0.12", "4.0.1"))
    findings, _ = _run(_lock("x", x=_entry("4.0.1")), fetch)
    assert findings == []


def test_versions_are_compared_as_numbers_and_not_as_text():
    fetch, _ = _registry(x=_versions("1.9.0", "1.10.0"))
    findings, _ = _run(_lock("x", x=_entry("1.9.0")), fetch)
    assert [f["newest"] for f in findings] == ["1.10.0"]
    # 1.9.0 is the higher one as text, so this is the other direction.
    fetch, _ = _registry(x=_versions("1.9.0", "1.10.0"))
    assert _run(_lock("x", x=_entry("1.10.0")), fetch)[0] == []


def test_a_locked_pre_release_is_below_its_release_and_above_the_line_before():
    fetch, _ = _registry(x=_versions("3.9.0", "4.0.0"))
    findings, _ = _run(_lock("x", x=_entry("4.0.0-beta6")), fetch)
    assert [f["newest"] for f in findings] == ["4.0.0"]
    fetch, _ = _registry(x=_versions("3.9.0"))
    assert _run(_lock("x", x=_entry("4.0.0-beta6")), fetch)[0] == []


def test_the_precedence_is_that_of_semver():
    """The order the semver specification gives."""
    ascending = (
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
    )
    keys = [outdated.version_key(v) for v in ascending]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)


def test_build_metadata_is_no_pre_release_and_does_not_count():
    assert outdated.version_key("1.0.0+build.5") == outdated.version_key("1.0.0")
    assert outdated.newest_stable({"1.0.0+build.5": {}}) == "1.0.0+build.5"


@pytest.mark.parametrize("version", ["1.0", "latest", "", "1.0.0.0", "v1.0.0"])
def test_what_is_no_semver_has_no_key_and_is_never_the_newest(version):
    assert outdated.version_key(version) is None
    assert outdated.newest_stable({version: {}, "1.0.0": {}}) == "1.0.0"


# --- the entries --------------------------------------------------------------


def test_a_scoped_name_is_encoded():
    fetch, calls = _registry(**{"@scope%2Fname": _versions("1.0.0", "1.1.0")})
    findings, _ = _run(_lock("@scope/name", **{"@scope/name": _entry("1.0.0")}), fetch)
    assert calls == [f"{outdated.REGISTRY}/@scope%2Fname"]
    assert [f["name"] for f in findings] == ["@scope/name"]


def test_the_request_asks_for_the_abbreviated_document(monkeypatch):
    seen = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b"{}"

    def urlopen(request, timeout):
        seen.append(request)
        return Response()

    monkeypatch.setattr(outdated.urllib.request, "urlopen", urlopen)
    assert outdated.fetch_url(f"{outdated.REGISTRY}/x") == (200, b"{}")
    assert seen[0].get_header("Accept") == "application/vnd.npm.install-v1+json"


def test_an_error_status_is_an_answer_and_no_exception(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "slow down", None, None)

    monkeypatch.setattr(outdated.urllib.request, "urlopen", urlopen)
    assert outdated.fetch_url(f"{outdated.REGISTRY}/x") == (429, b"")


def test_a_dev_entry_is_dev_and_a_dev_optional_entry_is_runtime():
    fetch, _ = _registry(
        a=_versions("1.0.0", "1.1.0"),
        b=_versions("1.0.0", "1.1.0"),
        c=_versions("1.0.0", "1.1.0"),
    )
    findings, _ = _run(
        _lock(
            a=_entry("1.0.0", dev=True),
            b=_entry("1.0.0", devOptional=True),
            c=_entry("1.0.0", optional=True),
        ),
        fetch,
    )
    assert {f["name"]: f["scope"] for f in findings} == {
        "a": "dev",
        "b": "runtime",
        "c": "runtime",
    }


def test_direct_comes_from_every_kind_of_dependency_of_the_root_entry():
    names = ("prod", "dev", "optional", "peer", "beneath")
    fetch, _ = _registry(**{n: _versions("1.0.0", "1.1.0") for n in names})
    packages = {
        "": {
            "dependencies": {"prod": "*"},
            "devDependencies": {"dev": "*"},
            "optionalDependencies": {"optional": "*"},
            "peerDependencies": {"peer": "*"},
        }
    } | {f"node_modules/{n}": _entry("1.0.0") for n in names}
    findings, _ = _run(packages, fetch)
    assert {f["name"]: f["direct"] for f in findings} == {
        "prod": True,
        "dev": True,
        "optional": True,
        "peer": True,
        "beneath": False,
    }


def test_a_nested_entry_of_a_direct_name_is_transitive():
    fetch, _ = _registry(x=_versions("1.0.0", "2.0.0", "2.1.0"), y=_versions("1.0.0"))
    packages = _lock("x", x=_entry("2.0.0"), y=_entry("1.0.0")) | {
        "node_modules/y/node_modules/x": _entry("1.0.0")
    }
    findings, status = _run(packages, fetch)
    assert {f["current"]: f["direct"] for f in findings} == {
        "2.0.0": True,
        "1.0.0": False,
    }
    assert status["checked"] == 3


def test_one_version_in_two_folders_is_one_finding_and_runtime_wins():
    fetch, calls = _registry(
        x=_versions("1.0.0", "1.1.0"), a=_versions("1.0.0"), b=_versions("1.0.0")
    )
    packages = _lock(a=_entry("1.0.0"), b=_entry("1.0.0")) | {
        "node_modules/a/node_modules/x": _entry("1.0.0", dev=True),
        "node_modules/b/node_modules/x": _entry("1.0.0"),
    }
    findings, _ = _run(packages, fetch)
    assert [(f["name"], f["scope"]) for f in findings] == [("x", "runtime")]
    assert len(calls) == 3


def test_an_alias_is_measured_as_the_package_it_is():
    fetch, calls = _registry(real=_versions("1.0.0", "1.1.0"))
    findings, _ = _run(
        _lock("alias", alias=_entry("1.0.0", name="real")),
        fetch,
    )
    assert calls == [f"{outdated.REGISTRY}/real"]
    assert [(f["name"], f["direct"]) for f in findings] == [("real", True)]


def test_a_workspace_member_is_the_repository_own_and_its_link_is_counted():
    fetch, calls = _registry(x=_versions("1.0.0"))
    packages = _lock(x=_entry("1.0.0")) | {
        "packages/a": {"name": "a", "version": "0.1.0"},
        "node_modules/a": {"resolved": "packages/a", "link": True},
    }
    findings, status = _run(packages, fetch)
    assert findings == []
    assert calls == [f"{outdated.REGISTRY}/x"]
    assert status["summary"] == (
        "1 locked package compared with the npm registry, 1 entry not from it left out."
    )


@pytest.mark.parametrize(
    "entry",
    [
        {"resolved": "../local", "link": True},
        _entry("1.0.0", resolved="git+ssh://git@example.com/example/x.git#abc"),
        _entry("1.0.0", resolved="file:../x-1.0.0.tgz"),
        _entry("1.0.0", resolved="https://npm.example.com/x/-/x-1.0.0.tgz"),
        {"version": "1.0.0", "inBundle": True},
        _entry("not-a-version"),
    ],
)
def test_an_entry_that_is_not_from_the_registry_is_counted_and_never_asked(entry):
    fetch, calls = _registry()
    findings, status = _run(_lock(x=entry), fetch)
    assert findings == []
    assert calls == []
    assert status == {
        "result": "ok",
        "checked": 0,
        "summary": (
            "0 locked packages compared with the npm registry, "
            "1 entry not from it left out."
        ),
    }


def test_an_entry_without_a_source_counts_as_from_the_registry():
    """npm writes it so with omit-lockfile-registry-resolved."""
    fetch, _ = _registry(x=_versions("1.0.0", "1.1.0"))
    findings, _ = _run(_lock(x={"version": "1.0.0"}), fetch)
    assert [f["newest"] for f in findings] == ["1.1.0"]


@pytest.mark.parametrize("answer", [404, {"name": "x", "time": {"unpublished": {}}}])
def test_a_package_the_registry_does_not_know_is_a_warning_and_counted(answer, capsys):
    fetch, _ = _registry(x=answer, y=_versions("1.0.0", "1.1.0"))
    findings, status = _run(_lock(x=_entry("1.0.0"), y=_entry("1.0.0")), fetch)
    assert [f["name"] for f in findings] == ["y"]
    assert status["result"] == "ok"
    assert status["checked"] == 2
    assert status["summary"] == (
        "1 locked package compared with the npm registry, 1 not known to it."
    )
    assert "::warning::The npm registry does not know x" in capsys.readouterr().out


# --- no answer ----------------------------------------------------------------


NO_ANSWER = [
    urllib.error.URLError("no route"),
    TimeoutError("timed out"),
    429,
    500,
    503,
    403,
    b"<html>not json</html>",
    b"[]",
    b'{"versions": {"1.0.0": "text"}}',
]


@pytest.mark.parametrize("answer", NO_ANSWER)
def test_no_answer_stops_the_run(answer):
    fetch, _ = _registry(x=answer)
    with pytest.raises(outdated.Unreachable):
        _run(_lock(x=_entry("1.0.0")), fetch)


def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lockfile: str) -> Path:
    out = tmp_path / "freshness-npm-outdated"
    monkeypatch.setenv("ROOT", str(tmp_path))
    monkeypatch.setenv("LOCKFILE", lockfile)
    monkeypatch.setenv("FINDINGS", str(out))
    return out


def _write(tmp_path: Path, packages: object, folder: str = ".") -> None:
    (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    (tmp_path / folder / "package-lock.json").write_text(
        json.dumps({"name": "example", "lockfileVersion": 3, "packages": packages}),
        "utf-8",
    )


@pytest.mark.parametrize("answer", NO_ANSWER)
def test_no_answer_leaves_inconclusive_and_no_findings_that_claim_a_clean_result(
    tmp_path, monkeypatch, answer
):
    _write(tmp_path, _lock(x=_entry("1.0.0")))
    out = _env(tmp_path, monkeypatch, "./package-lock.json")
    fetch, _ = _registry(x=answer)
    monkeypatch.setattr(outdated, "fetch_url", fetch)
    assert outdated.main() == 0
    assert not (out / "findings.jsonl").exists()
    status = json.loads((out / "status.json").read_text("utf-8"))
    assert status["result"] == "inconclusive"
    assert status["summary"].endswith(": x.")
    assert "http" not in status["summary"]


def test_one_package_without_an_answer_drops_the_findings_of_the_others(
    tmp_path, monkeypatch
):
    _write(tmp_path, _lock(a=_entry("1.0.0"), b=_entry("1.0.0")))
    out = _env(tmp_path, monkeypatch, "package-lock.json")
    fetch, _ = _registry(a=_versions("1.0.0", "1.1.0"), b=429)
    monkeypatch.setattr(outdated, "fetch_url", fetch)
    assert outdated.main() == 0
    assert not (out / "findings.jsonl").exists()


# --- the lockfile -------------------------------------------------------------


def _script(tmp_path: Path, lockfile: str):
    return subprocess.run(
        [sys.executable, str(FOLDER / "npm_outdated.py")],
        env=os.environ
        | {
            "ROOT": str(tmp_path),
            "LOCKFILE": lockfile,
            "FINDINGS": str(tmp_path / "out"),
        },
        capture_output=True,
        text=True,
    )


def test_a_missing_lockfile_fails_and_leaves_nothing(tmp_path):
    run = _script(tmp_path, "assets/vendor/package-lock.json")
    assert run.returncode == 1
    assert "::error::Could not read" in run.stderr
    assert not (tmp_path / "out").exists()


def test_a_lockfile_of_version_1_fails_with_a_word(tmp_path):
    (tmp_path / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 1, "dependencies": {"x": {"version": "1.0.0"}}}),
        "utf-8",
    )
    run = _script(tmp_path, "package-lock.json")
    assert run.returncode == 1
    assert "no packages key" in run.stderr
    assert "npm install --package-lock-only" in run.stderr
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("text", ["{not json", "[]", '{"packages": []}'])
def test_a_lockfile_that_cannot_be_read_fails(tmp_path, text):
    (tmp_path / "package-lock.json").write_text(text, "utf-8")
    assert _script(tmp_path, "package-lock.json").returncode == 1


def test_a_lockfile_without_packages_to_ask_for_is_ok(tmp_path):
    _write(tmp_path, {"": {"name": "example"}})
    run = _script(tmp_path, "package-lock.json")
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "out" / "findings.jsonl").read_text("utf-8") == ""
    status = json.loads((tmp_path / "out" / "status.json").read_text("utf-8"))
    assert status["result"] == "ok"
    assert status["checked"] == 0


# --- through the real report --------------------------------------------------


def test_the_output_passes_through_the_real_report(tmp_path, monkeypatch):
    _write(
        tmp_path,
        _lock(
            "htmx.org",
            **{
                "htmx.org": _entry("4.0.0"),
                "beneath": _entry("1.0.0"),
                "tooling": _entry("1.0.0", dev=True),
                "local": {"resolved": "../local", "link": True},
            },
        ),
        "assets/vendor",
    )
    results = tmp_path / "results"
    monkeypatch.setenv("ROOT", str(tmp_path))
    monkeypatch.setenv("LOCKFILE", "assets/vendor/package-lock.json")
    monkeypatch.setenv("FINDINGS", str(results / "freshness-npm-outdated"))
    fetch, _ = _registry(
        **{
            "htmx.org": HTMX,
            "beneath": _versions("1.0.0", "1.1.0"),
            "tooling": _versions("1.0.0", "2.0.0"),
        }
    )
    monkeypatch.setattr(outdated, "fetch_url", fetch)
    assert outdated.main() == 0

    loaded = report.load_results(results, ["npm-outdated"])
    (finding,) = [f for f in loaded[0].findings if f.name == "htmx.org"]
    assert finding.where == ("assets/vendor/package-lock.json",)
    assert finding.within_bounds is None
    text = report.render(loaded, [], False, "", "report")
    assert "| `htmx.org` | 4.0.0 | 4.0.1 | patch |" in text
    assert "`tooling`" not in text
    assert "`beneath`" not in text
    assert "3 locked packages compared with the npm registry" in text
    assert "1 entry not from it left out" in text


def test_a_run_without_an_answer_never_lets_the_report_close_the_issue(
    tmp_path, monkeypatch
):
    _write(tmp_path, _lock(x=_entry("1.0.0")))
    results = tmp_path / "results"
    monkeypatch.setenv("ROOT", str(tmp_path))
    monkeypatch.setenv("LOCKFILE", "package-lock.json")
    monkeypatch.setenv("FINDINGS", str(results / "freshness-npm-outdated"))
    fetch, _ = _registry(x=503)
    monkeypatch.setattr(outdated, "fetch_url", fetch)
    assert outdated.main() == 0

    loaded = report.load_results(results, ["npm-outdated"])
    text = report.render(loaded, [], False, "", "report")
    assert "`npm-outdated` ran but could not prove anything" in text
    assert "The npm registry answered 503: x." in text


def test_a_clean_run_leaves_the_report_empty_so_the_issue_closes(tmp_path, monkeypatch):
    _write(tmp_path, _lock("x", x=_entry("1.0.0")))
    results = tmp_path / "results"
    monkeypatch.setenv("ROOT", str(tmp_path))
    monkeypatch.setenv("LOCKFILE", "package-lock.json")
    monkeypatch.setenv("FINDINGS", str(results / "freshness-npm-outdated"))
    fetch, _ = _registry(x=_versions("1.0.0"))
    monkeypatch.setattr(outdated, "fetch_url", fetch)
    assert outdated.main() == 0

    loaded = report.load_results(results, ["npm-outdated"])
    assert report.render(loaded, [], False, "", "report") == ""


# --- the action ---------------------------------------------------------------


def test_the_action_takes_the_inputs_of_the_python_action():
    assert set(ACTION["inputs"]) == {"findings", "directory"}
    assert ACTION["inputs"]["findings"]["required"] is True
    assert ACTION["inputs"]["directory"]["default"] == "."


def test_the_action_runs_the_script_and_installs_nothing_of_node():
    steps = ACTION["runs"]["steps"]
    (setup,) = [s for s in steps if "uses" in s]
    assert setup["uses"].startswith("astral-sh/setup-uv@")
    assert setup["with"]["enable-cache"] is False
    (step,) = [s for s in steps if "run" in s]
    assert step["run"] == (
        'uv run --no-project --python ">=3.11" "$GITHUB_ACTION_PATH/npm_outdated.py"'
    )
    assert step["env"] == {
        "LOCKFILE": "${{ inputs.directory }}/package-lock.json",
        "FINDINGS": "${{ inputs.findings }}",
    }
