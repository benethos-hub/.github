"""What the scanner actions and the workflows around them share, for their tests.

Each scanner action ends in a call of sarif-report, and each reusable
workflow is one job of checkout and action that mirrors the action's inputs
without the token, plus the runner and the time limit.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SHARED = ("failure-level", "category", "upload", "artifact", "retention-days", "token")
WORKFLOW_ONLY = ("runs-on", "timeout-minutes")


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text("utf-8"))


def step(action: dict, name: str) -> dict:
    (found,) = [s for s in action["runs"]["steps"] if s.get("name") == name]
    return found


def assert_inputs_are_described(action: dict) -> None:
    for name, spec in action["inputs"].items():
        assert spec["description"], name
        assert spec["required"] is False, name
        assert "default" in spec, name
    assert set(SHARED) <= set(action["inputs"])
    assert action["inputs"]["upload"]["default"] == "true"
    assert action["inputs"]["retention-days"]["default"] == "7"
    assert action["inputs"]["token"]["default"] == "${{ github.token }}"


def assert_reports_through_sarif_report(action: dict, sarif: str, tool: str) -> None:
    report = action["runs"]["steps"][-1]
    assert report["name"] == "Report"
    assert report["id"] == "report"
    assert report["uses"] == "benethos-hub/.github/actions/sarif-report@main"
    expected = {"sarif": sarif, "tool": tool}
    expected |= {name: f"${{{{ inputs.{name} }}}}" for name in SHARED}
    assert report["with"] == expected
    assert action["outputs"]["sarif"]["value"] == sarif
    assert (
        action["outputs"]["findings"]["value"] == "${{ steps.report.outputs.findings }}"
    )
    assert (
        action["outputs"]["highest"]["value"] == "${{ steps.report.outputs.highest }}"
    )


def assert_installs_uv_first(action: dict) -> None:
    first = action["runs"]["steps"][0]
    assert first["uses"].startswith("astral-sh/setup-uv@")
    assert first["with"] == {"enable-cache": False}


def assert_workflow_mirrors_action(
    workflow: dict, action: dict, job: str, name: str, uses: str
) -> None:
    inputs = workflow[True]["workflow_call"]["inputs"]
    shared = set(action["inputs"]) - {"token"}
    assert set(inputs) == shared | set(WORKFLOW_ONLY)
    for key in shared:
        spec = inputs[key]
        assert spec["description"] == action["inputs"][key]["description"], key
        if spec["type"] == "boolean":
            assert str(spec["default"]).lower() == action["inputs"][key]["default"], key
        elif spec["type"] == "number":
            assert str(spec["default"]) == action["inputs"][key]["default"], key
        else:
            assert spec["type"] == "string", key
            assert spec["default"] == action["inputs"][key]["default"], key
    assert inputs["upload"]["type"] == "boolean"
    assert inputs["retention-days"]["type"] == "number"
    assert inputs["runs-on"]["default"] == "ubuntu-latest"
    assert inputs["timeout-minutes"]["type"] == "number"

    assert list(workflow["jobs"]) == [job]
    the_job = workflow["jobs"][job]
    permissions = {"contents": "read", "security-events": "write"}
    assert workflow["permissions"] == permissions
    assert the_job["permissions"] == permissions
    assert the_job["name"] == name
    assert the_job["runs-on"] == "${{ inputs.runs-on }}"
    assert the_job["timeout-minutes"] == "${{ inputs.timeout-minutes }}"
    checkout, call = the_job["steps"]
    assert checkout["uses"].startswith("actions/checkout@")
    assert call["uses"] == uses
    assert call["with"] == {key: f"${{{{ inputs.{key} }}}}" for key in shared}


def assert_pinned_download(
    action: dict, step_name: str, version_key: str, sha_key: str, pin_name: str
) -> None:
    """The install step pins version and checksum, checks the checksum, and
    download-pins.yml knows the pin."""
    install = step(action, step_name)
    assert install["env"][version_key].startswith("v")
    assert len(install["env"][sha_key]) == 64
    assert f"${{{sha_key}}}" in install["run"] or f"${sha_key}" in install["run"]
    assert "sha256sum -c -" in install["run"]
    assert "set -euo pipefail" in install["run"]
    pins = yaml.safe_load((ROOT / ".github" / "download-pins.yml").read_text("utf-8"))
    (pin,) = [p for p in pins if p["name"] == pin_name]
    assert pin["version"] == version_key
    assert pin["sha256"] == sha_key


def assert_reports_only_by_default(action: dict) -> None:
    """A scanner fails nothing on its own, the code scanning check decides."""
    spec = action["inputs"]["failure-level"]
    assert spec["default"] == "none"
    assert "none, the default, fails nothing" in spec["description"]
    assert "code scanning check" in spec["description"]


def assert_documented(action: dict, page: str, *files: str) -> None:
    for name in action["inputs"]:
        assert f"`{name}`" in page, name
    for file in files:
        assert file in page, file
