"""The npm audit adapter of the freshness report: which entries of the audit are
findings, and what an audit without an answer leaves behind. The canned answers
have the shape npm 11.20 printed on 2026-11-05.
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
FOLDER = ROOT / "actions" / "node" / "freshness-audit"
ACTION = yaml.safe_load((FOLDER / "action.yml").read_text("utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


audit = _load("freshness_node_audit", FOLDER / "npm_audit.py")
report = _load(
    "freshness_report_for_npm_audit",
    ROOT / "actions" / "freshness" / "report" / "report.py",
)

VULN = "GHSA-vh95-rmgr-6w4m"
OTHER = "GHSA-xvch-5gv4-984h"

# minimist 1.2.8 at the top and 0.0.8 beneath mkdirp, as npm locks them.
PACKAGES = {
    "": {"name": "example", "dependencies": {"minimist": "1.2.8", "mkdirp": "0.5.1"}},
    "node_modules/minimist": {"version": "1.2.8"},
    "node_modules/mkdirp": {"version": "0.5.1"},
    "node_modules/mkdirp/node_modules/minimist": {"version": "0.0.8"},
}


def _advisory(ghsa: str = VULN, name: str = "minimist") -> dict[str, object]:
    return {
        "source": 1096466,
        "name": name,
        "dependency": name,
        "title": "Prototype Pollution",
        "url": f"https://github.com/advisories/{ghsa}",
        "severity": "critical",
        "range": "<0.2.1",
    }


def _vulnerability(*via: object, **fields: object) -> dict[str, object]:
    return {
        "name": "minimist",
        "severity": "critical",
        "isDirect": False,
        "via": list(via),
        "effects": ["mkdirp"],
        "range": "<=0.2.3",
        "nodes": ["node_modules/mkdirp/node_modules/minimist"],
        "fixAvailable": True,
    } | fields


def _output(**vulnerabilities: dict[str, object]) -> str:
    return json.dumps(
        {
            "auditReportVersion": 2,
            "vulnerabilities": vulnerabilities,
            "metadata": {"vulnerabilities": {"total": len(vulnerabilities)}},
        }
    )


# As npm prints them when the endpoint gave no answer.
REFUSED = json.dumps(
    {
        "message": "request to https://registry.npmjs.org/-/npm/v1/security/advisories/"
        "bulk failed, reason: connect ECONNREFUSED",
        "error": {"summary": "", "detail": ""},
    }
)


def _status(code: int) -> str:
    return json.dumps(
        {
            "message": f"{code} - POST https://registry.npmjs.org/-/npm/v1/security",
            "method": "POST",
            "uri": "https://registry.npmjs.org/-/npm/v1/security/advisories/bulk",
            "headers": {"server": ["example"]},
            "statusCode": code,
            "body": {"error": "nope"},
            "error": {"summary": "", "detail": ""},
        }
    )


def _findings(vulnerabilities: dict[str, object], ignore: frozenset[str] = frozenset()):
    return audit.findings_of(
        vulnerabilities, PACKAGES, "package-lock.json", set(ignore)
    )


# --- the findings -------------------------------------------------------------


def test_an_advisory_is_a_finding_with_the_version_from_the_lockfile():
    assert _findings({"minimist": _vulnerability(_advisory())}) == [
        {
            "category": "vulnerability",
            "name": "minimist",
            "where": ["package-lock.json"],
            "current": "0.0.8",
            "vulnerability": VULN,
        }
    ]


def test_each_advisory_is_a_finding_of_its_own():
    found = _findings({"minimist": _vulnerability(_advisory(), _advisory(OTHER))})
    assert [f["vulnerability"] for f in found] == [VULN, OTHER]


def test_a_string_in_via_only_points_at_another_package_and_is_skipped():
    found = _findings(
        {
            "minimist": _vulnerability(_advisory()),
            "mkdirp": _vulnerability(
                "minimist", name="mkdirp", nodes=["node_modules/mkdirp"]
            ),
        }
    )
    assert [f["name"] for f in found] == ["minimist"]


def test_two_affected_versions_are_named_each():
    packages = PACKAGES | {
        "node_modules/other/node_modules/minimist": {"version": "0.1.0"}
    }
    found = audit.findings_of(
        {
            "minimist": _vulnerability(
                _advisory(),
                nodes=[
                    "node_modules/mkdirp/node_modules/minimist",
                    "node_modules/other/node_modules/minimist",
                ],
            )
        },
        packages,
        "package-lock.json",
        set(),
    )
    assert [f["current"] for f in found] == ["0.0.8", "0.1.0"]


def test_the_same_version_in_two_folders_is_one_finding():
    packages = PACKAGES | {
        "node_modules/other/node_modules/minimist": {"version": "0.0.8"}
    }
    found = audit.findings_of(
        {
            "minimist": _vulnerability(
                _advisory(),
                nodes=[
                    "node_modules/mkdirp/node_modules/minimist",
                    "node_modules/other/node_modules/minimist",
                ],
            )
        },
        packages,
        "package-lock.json",
        set(),
    )
    assert [f["current"] for f in found] == ["0.0.8"]


def test_a_fix_of_the_same_package_is_named():
    fix = {"name": "minimist", "version": "1.2.8", "isSemVerMajor": True}
    (found,) = _findings({"minimist": _vulnerability(_advisory(), fixAvailable=fix)})
    assert found["fix"] == ["1.2.8"]


@pytest.mark.parametrize(
    "fix",
    [
        # Measured: npm names the parent when only moving it helps.
        {"name": "mkdirp", "version": "0.5.6", "isSemVerMajor": False},
        True,
        False,
    ],
)
def test_a_fix_that_names_no_version_of_the_package_is_left_out(fix):
    (found,) = _findings({"minimist": _vulnerability(_advisory(), fixAvailable=fix)})
    assert "fix" not in found


def test_a_waived_id_is_dropped_and_the_other_stays():
    found = _findings(
        {"minimist": _vulnerability(_advisory(), _advisory(OTHER))},
        frozenset({VULN}),
    )
    assert [f["vulnerability"] for f in found] == [OTHER]


def test_an_advisory_url_without_a_ghsa_id_stays_a_finding_named_by_its_url():
    advisory = _advisory() | {"url": "https://example.com/advisory/7"}
    (found,) = _findings({"minimist": _vulnerability(advisory)})
    assert found["vulnerability"] == "https://example.com/advisory/7"


def test_no_vulnerabilities_are_no_findings():
    assert _findings(audit.read_audit(_output())) == []


def test_a_name_the_lockfile_does_not_hold_is_an_error():
    with pytest.raises(ValueError, match="the lockfile does not"):
        _findings({"minimist": _vulnerability(_advisory(), nodes=["node_modules/no"])})


def test_an_advisory_without_a_url_is_an_error():
    advisory = _advisory()
    del advisory["url"]
    with pytest.raises(ValueError, match="without a URL"):
        _findings({"minimist": _vulnerability(advisory)})


# --- the output of npm --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (REFUSED, "gave no result."),
        (_status(429), "It answered 429."),
        (_status(500), "It answered 500."),
        (_status(403), "It answered 403."),
        (_status(404), "It answered 404."),
    ],
)
def test_an_endpoint_without_an_answer_is_named_and_no_address_is(text, said):
    with pytest.raises(audit.Unreachable, match=said) as caught:
        audit.read_audit(text)
    assert "http" not in str(caught.value)


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("", "printed nothing"),
        ("not json", "Expecting value"),
        ("[]", "no object"),
        ('{"error": {"code": "ENOLOCK"}}', "ENOLOCK"),
        ("{}", "no report"),
    ],
)
def test_anything_else_is_an_error(text, word):
    with pytest.raises(ValueError, match=word):
        audit.read_audit(text)


# --- the script ---------------------------------------------------------------


def _write_lock(folder: Path, packages: object = PACKAGES) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": packages}), "utf-8"
    )


def _script(tmp_path: Path, output: str, lockfile: str = "package-lock.json", **env):
    out = tmp_path / "results" / "freshness-npm-audit"
    answer = tmp_path / "audit.json"
    answer.write_text(output, "utf-8")
    return out, subprocess.run(
        [sys.executable, str(FOLDER / "npm_audit.py")],
        env=os.environ
        | {
            "ROOT": str(tmp_path),
            "LOCKFILE": lockfile,
            "AUDIT": str(answer),
            "FINDINGS": str(out),
        }
        | env,
        capture_output=True,
        text=True,
    )


def test_the_script_writes_the_findings_with_the_folder_in_where(tmp_path):
    _write_lock(tmp_path / "assets" / "vendor")
    out, run = _script(
        tmp_path,
        _output(minimist=_vulnerability(_advisory())),
        "./assets/vendor/package-lock.json",
    )
    assert run.returncode == 0, run.stderr
    (line,) = (out / "findings.jsonl").read_text("utf-8").splitlines()
    assert json.loads(line)["where"] == ["assets/vendor/package-lock.json"]
    status = json.loads((out / "status.json").read_text("utf-8"))
    assert status == {"result": "ok", "checked": 3}
    assert "3 pinned versions audited, 1 known vulnerabilities." in run.stdout


def test_the_script_takes_the_waivers_from_the_environment(tmp_path):
    _write_lock(tmp_path)
    out, run = _script(
        tmp_path,
        _output(minimist=_vulnerability(_advisory(), _advisory(OTHER))),
        IGNORE_VULNS=f"{VULN} {OTHER}",
    )
    assert run.returncode == 0, run.stderr
    assert (out / "findings.jsonl").read_text("utf-8") == ""


def test_a_link_counts_for_nothing_in_the_status(tmp_path):
    _write_lock(
        tmp_path,
        {
            "": {"name": "example"},
            "packages/a": {"name": "a", "version": "0.1.0"},
            "node_modules/a": {"resolved": "packages/a", "link": True},
        },
    )
    out, run = _script(tmp_path, _output())
    assert run.returncode == 0, run.stderr
    assert json.loads((out / "status.json").read_text("utf-8"))["checked"] == 0


@pytest.mark.parametrize("output", [REFUSED, _status(429), _status(500)])
def test_an_unreachable_endpoint_is_inconclusive_and_claims_no_clean_result(
    tmp_path, output
):
    _write_lock(tmp_path)
    out, run = _script(tmp_path, output)
    assert run.returncode == 0, run.stderr
    assert not (out / "findings.jsonl").exists()
    status = json.loads((out / "status.json").read_text("utf-8"))
    assert status["result"] == "inconclusive"
    assert "http" not in status["summary"]


@pytest.mark.parametrize("output", ["", "not json", '{"error": {"code": "ENOLOCK"}}'])
def test_output_that_cannot_be_read_fails_and_leaves_nothing(tmp_path, output):
    _write_lock(tmp_path)
    out, run = _script(tmp_path, output)
    assert run.returncode == 1
    assert "::error::Could not read the npm audit output" in run.stderr
    assert not out.exists()


def test_a_missing_lockfile_fails(tmp_path):
    out, run = _script(tmp_path, _output())
    assert run.returncode == 1
    assert "::error::Could not read" in run.stderr
    assert not out.exists()


def test_a_lockfile_of_version_1_fails_with_a_word(tmp_path):
    (tmp_path / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 1, "dependencies": {}}), "utf-8"
    )
    out, run = _script(tmp_path, _output())
    assert run.returncode == 1
    assert "no packages key" in run.stderr
    assert not out.exists()


# --- through the real report --------------------------------------------------


def test_the_output_passes_through_the_real_report(tmp_path):
    _write_lock(tmp_path / "assets" / "vendor")
    fix = {"name": "minimist", "version": "1.2.8", "isSemVerMajor": True}
    out, run = _script(
        tmp_path,
        _output(minimist=_vulnerability(_advisory(), fixAvailable=fix)),
        "assets/vendor/package-lock.json",
    )
    assert run.returncode == 0, run.stderr
    loaded = report.load_results(out.parent, ["npm-audit"])
    (finding,) = loaded[0].findings
    assert finding.where == ("assets/vendor/package-lock.json",)
    text = report.render(loaded, [], False, "", "report")
    assert "### Known vulnerabilities" in text
    assert f"| `minimist` | 0.0.8 | {VULN} | 1.2.8 |" in text


def test_a_vulnerability_without_a_fix_passes_through_the_real_report(tmp_path):
    _write_lock(tmp_path)
    out, run = _script(tmp_path, _output(minimist=_vulnerability(_advisory())))
    assert run.returncode == 0, run.stderr
    loaded = report.load_results(out.parent, ["npm-audit"])
    assert VULN in report.render(loaded, [], False, "", "report")


def test_an_audit_without_an_answer_never_lets_the_report_close_the_issue(tmp_path):
    _write_lock(tmp_path)
    out, run = _script(tmp_path, _status(503))
    assert run.returncode == 0, run.stderr
    loaded = report.load_results(out.parent, ["npm-audit"])
    text = report.render(loaded, [], False, "", "report")
    assert "`npm-audit` ran but could not prove anything" in text
    assert "The npm audit endpoint gave no result. It answered 503." in text


def test_a_clean_audit_leaves_the_report_empty_so_the_issue_closes(tmp_path):
    _write_lock(tmp_path)
    out, run = _script(tmp_path, _output())
    assert run.returncode == 0, run.stderr
    loaded = report.load_results(out.parent, ["npm-audit"])
    assert report.render(loaded, [], False, "", "report") == ""


# --- the action ---------------------------------------------------------------


def _bash_step() -> dict[str, object]:
    (step,) = [s for s in ACTION["runs"]["steps"] if "npm audit" in s.get("run", "")]
    return step


def test_the_action_takes_the_inputs_of_the_python_action():
    assert set(ACTION["inputs"]) == {"findings", "directory", "ignore-vulns"}
    assert ACTION["inputs"]["findings"]["required"] is True
    assert ACTION["inputs"]["directory"]["default"] == "."
    assert ACTION["inputs"]["ignore-vulns"]["default"] == ""


def test_the_action_audits_from_the_lockfile_and_ignores_the_exit_code():
    run = _bash_step()["run"]
    assert "npm audit --json --package-lock-only --include=dev >" in run
    assert '"$WORK/audit.json" || true' in run
    assert "Missing package-lock.json" in run
    assert 'cd "$DIRECTORY" || exit 1' in run


def test_the_action_installs_no_package_and_runs_no_fix():
    for step in ACTION["runs"]["steps"]:
        run = step.get("run", "")
        for word in ("npm ci", "npm install", "npm i ", "audit fix", "npx "):
            assert word not in run


def test_the_action_hands_its_inputs_to_the_script():
    (setup,) = [s for s in ACTION["runs"]["steps"] if "uses" in s]
    assert setup["uses"].startswith("astral-sh/setup-uv@")
    assert setup["with"]["enable-cache"] is False
    (step,) = [s for s in ACTION["runs"]["steps"] if "npm_audit.py" in s.get("run", "")]
    assert step["run"] == (
        'uv run --no-project --python ">=3.11" "$GITHUB_ACTION_PATH/npm_audit.py"'
    )
    assert step["env"]["LOCKFILE"] == "${{ inputs.directory }}/package-lock.json"
    assert step["env"]["IGNORE_VULNS"] == "${{ inputs.ignore-vulns }}"
    assert step["env"]["FINDINGS"] == "${{ inputs.findings }}"
    assert step["env"]["AUDIT"].endswith("/audit.json")
    assert step["env"]["AUDIT"].startswith(_bash_step()["env"]["WORK"])
