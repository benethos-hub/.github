"""The CodeQL action and the workflow around it: every input goes through to
github/codeql-action, the workflow mirrors the action, and the documentation
names all of it.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION_PATH = ROOT / "actions" / "codeql" / "action.yml"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "codeql.yml"
ACTION = yaml.safe_load(ACTION_PATH.read_text("utf-8"))
WORKFLOW = yaml.safe_load(WORKFLOW_PATH.read_text("utf-8"))
INPUTS = ACTION["inputs"]
WORKFLOW_INPUTS = WORKFLOW[True]["workflow_call"]["inputs"]
JOB = WORKFLOW["jobs"]["codeql"]
PAGE = (ROOT / "docs" / "codeql.md").read_text("utf-8")

INIT_INPUTS = (
    "languages",
    "queries",
    "packs",
    "config-file",
    "config",
    "build-mode",
    "tools",
    "ram",
    "threads",
    "debug",
    "token",
)
ANALYZE_INPUTS = ("category", "upload", "upload-database", "ram", "threads", "token")
WORKFLOW_ONLY = ("runs-on", "timeout-minutes")


def _step(name: str) -> dict:
    (step,) = [s for s in ACTION["runs"]["steps"] if s["name"] == name]
    return step


def test_every_input_has_a_description_and_a_default():
    assert set(INPUTS) == {*INIT_INPUTS, *ANALYZE_INPUTS}
    for name, spec in INPUTS.items():
        assert spec["description"], name
        assert spec["required"] is False, name
        assert "default" in spec, name
    assert INPUTS["languages"]["default"] == "python,actions"
    assert INPUTS["queries"]["default"] == "security-and-quality"
    assert INPUTS["category"]["default"] == "codeql"
    assert INPUTS["upload"]["default"] == "always"
    assert INPUTS["upload-database"]["default"] == "false"
    assert INPUTS["debug"]["default"] == "false"
    assert INPUTS["token"]["default"] == "${{ github.token }}"
    for name in (
        "packs",
        "config-file",
        "config",
        "build-mode",
        "tools",
        "ram",
        "threads",
    ):
        assert INPUTS[name]["default"] == "", name


def test_init_and_analyze_are_the_same_release_and_get_every_input():
    init = _step("Prepare the analysis")
    analyze = _step("Analyse and upload")
    assert list(ACTION["runs"]["steps"]) == [init, analyze]
    init_ref = init["uses"].removeprefix("github/codeql-action/init@")
    analyze_ref = analyze["uses"].removeprefix("github/codeql-action/analyze@")
    assert re.fullmatch(r"[0-9a-f]{40}", init_ref)
    assert init_ref == analyze_ref
    pin = r"github/codeql-action/\w+@[0-9a-f]{40} # (v[\d.]+)"
    versions = re.findall(pin, ACTION_PATH.read_text("utf-8"))
    assert len(versions) == 2 and len(set(versions)) == 1
    for name in INIT_INPUTS:
        assert init["with"][name] == f"${{{{ inputs.{name} }}}}", name
    assert set(init["with"]) == set(INIT_INPUTS)
    assert analyze["id"] == "analyze"
    for name in ANALYZE_INPUTS:
        if name != "upload":
            assert analyze["with"][name] == f"${{{{ inputs.{name} }}}}", name
    assert set(analyze["with"]) == set(ANALYZE_INPUTS)


def test_a_pull_request_from_a_fork_never_uploads():
    upload = _step("Analyse and upload")["with"]["upload"]
    assert "github.event_name == 'pull_request'" in upload
    assert "github.event.pull_request.head.repo.fork" in upload
    assert upload.endswith("&& 'never' || inputs.upload }}")


def test_the_outputs_come_from_the_analysis():
    outputs = ACTION["outputs"]
    assert outputs["sarif"]["value"] == "${{ steps.analyze.outputs.sarif-output }}"
    assert outputs["sarif-id"]["value"] == "${{ steps.analyze.outputs.sarif-id }}"


def test_the_workflow_mirrors_the_action():
    shared = set(INPUTS) - {"token"}
    assert set(WORKFLOW_INPUTS) == shared | set(WORKFLOW_ONLY)
    for name in shared:
        spec = WORKFLOW_INPUTS[name]
        assert spec["description"] == INPUTS[name]["description"], name
        default = spec["default"]
        if spec["type"] == "boolean":
            assert str(default).lower() == INPUTS[name]["default"], name
        else:
            assert spec["type"] == "string", name
            assert default == INPUTS[name]["default"], name
    assert WORKFLOW_INPUTS["upload-database"]["type"] == "boolean"
    assert WORKFLOW_INPUTS["debug"]["type"] == "boolean"
    assert WORKFLOW_INPUTS["runs-on"] == {
        "description": "The runner of the job.",
        "type": "string",
        "default": "ubuntu-latest",
    }
    assert WORKFLOW_INPUTS["timeout-minutes"]["type"] == "number"
    assert WORKFLOW_INPUTS["timeout-minutes"]["default"] == 30


def test_the_job_checks_out_grants_the_upload_and_passes_everything_through():
    assert list(WORKFLOW["jobs"]) == ["codeql"]
    assert WORKFLOW["permissions"] == {"contents": "read", "security-events": "write"}
    assert JOB["permissions"] == {"contents": "read", "security-events": "write"}
    assert JOB["name"] == "CodeQL"
    assert JOB["runs-on"] == "${{ inputs.runs-on }}"
    assert JOB["timeout-minutes"] == "${{ inputs.timeout-minutes }}"
    checkout, codeql = JOB["steps"]
    assert checkout["uses"].startswith("actions/checkout@")
    assert codeql["uses"] == "benethos-hub/.github/actions/codeql@main"
    shared = set(INPUTS) - {"token"}
    assert set(codeql["with"]) == shared
    for name in shared:
        assert codeql["with"][name] == f"${{{{ inputs.{name} }}}}", name


def test_the_documentation_names_every_input_and_both_files():
    for name in (*INPUTS, *WORKFLOW_ONLY):
        assert f"`{name}`" in PAGE, name
    assert "../actions/codeql/action.yml" in PAGE
    assert "../.github/workflows/codeql.yml" in PAGE
    assert "code-scanning/default-setup -f state=not-configured" in PAGE
    assert "(docs/codeql.md)" in (ROOT / "README.md").read_text("utf-8")
    assert "codeql.md" in (ROOT / "docs" / "repository-settings.md").read_text("utf-8")
    assert "codeql.yml" in (ROOT / "docs" / "ci.md").read_text("utf-8")
    assert "codeql.md" in (ROOT / "docs" / "new-repository.md").read_text("utf-8")
    assert "`codeql.yml` calls `codeql`" in (
        ROOT / "docs" / "maintaining.md"
    ).read_text("utf-8")
