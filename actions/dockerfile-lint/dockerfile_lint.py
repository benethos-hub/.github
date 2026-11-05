"""Run hadolint over the Dockerfiles of the checkout and leave a SARIF file.

Environment: HADOLINT names the binary, FILES the glob patterns of the files
(whitespace separated, relative to the working directory), IGNORE the rule
codes to leave out, TRUSTED_REGISTRIES the registries FROM may pull from,
CONFIG a .hadolint.yaml, OUT the SARIF file to write. Without a matching file
the SARIF is empty, so an upload closes earlier alerts, and nothing fails.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TOOL = "Hadolint"


def find_files(root: Path, patterns: list[str]) -> list[str]:
    """The files beneath ``root`` that match a pattern, relative and sorted.
    Anything under .git is left out."""
    found: set[str] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and ".git" not in path.relative_to(root).parts:
                found.add(path.relative_to(root).as_posix())
    return sorted(found)


def command(
    binary: str,
    files: list[str],
    ignore: list[str],
    registries: list[str],
    config: str,
) -> list[str]:
    """The hadolint call. --no-fail leaves the verdict to the report."""
    args = [binary, "--no-fail", "--no-color", "--format", "sarif"]
    for rule in ignore:
        args += ["--ignore", rule]
    for registry in registries:
        args += ["--trusted-registry", registry]
    if config:
        args += ["--config", config]
    return [*args, "--", *files]


def empty_sarif(tool: str) -> dict[str, object]:
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": tool}}, "results": []}],
    }


def main() -> int:
    out = Path(os.environ["OUT"])
    patterns = os.environ.get("FILES", "").split() or ["**/Dockerfile*"]
    files = find_files(Path.cwd(), patterns)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not files:
        out.write_text(json.dumps(empty_sarif(TOOL)), "utf-8")
        print(f"::notice::No file matches {' '.join(patterns)}. Nothing to lint.")
        return 0
    args = command(
        os.environ.get("HADOLINT") or "hadolint",
        files,
        os.environ.get("IGNORE", "").split(),
        os.environ.get("TRUSTED_REGISTRIES", "").split(),
        os.environ.get("CONFIG", ""),
    )
    run = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    if run.returncode != 0:
        print(f"::error::hadolint failed: {run.stderr.strip() or run.returncode}")
        return 1
    out.write_text(run.stdout, "utf-8")
    print(f"hadolint read {len(files)} file{'' if len(files) == 1 else 's'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
