"""Run Checkov from the lockfile of the action and leave a SARIF file.

Environment: ACTION_PATH is the folder with pyproject.toml and uv.lock,
DIRECTORY the folder to scan, FRAMEWORK the frameworks, CHECK and SKIP_CHECK
the check ids to run or to leave out, SKIP_PATH the path patterns to leave
out, CONFIG_FILE a .checkov.yaml, EXTERNAL_CHECKS a folder of custom checks,
OUT_DIR where Checkov writes results_sarif.sarif. Checkov runs with
--soft-fail, the verdict is the report's, and with --skip-download, so
nothing reaches the vendor's platform.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SARIF_NAME = "results_sarif.sarif"


def command(env: dict[str, str]) -> list[str]:
    """The checkov call from the environment, through uv and the lockfile."""
    args = [
        "uv",
        "run",
        "--quiet",
        "--frozen",
        "--project",
        env["ACTION_PATH"],
        "checkov",
        "--directory",
        env.get("DIRECTORY") or ".",
        "--skip-download",
        "--soft-fail",
        "--quiet",
        "--compact",
        "--output",
        "cli",
        "--output",
        "sarif",
        "--output-file-path",
        env["OUT_DIR"],
    ]
    frameworks = env.get("FRAMEWORK", "").split()
    if frameworks:
        args += ["--framework", *frameworks]
    for key, flag in (("CHECK", "--check"), ("SKIP_CHECK", "--skip-check")):
        value = ",".join(env.get(key, "").replace(",", " ").split())
        if value:
            args += [flag, value]
    for path in env.get("SKIP_PATH", "").split():
        args += ["--skip-path", path]
    if env.get("CONFIG_FILE"):
        args += ["--config-file", env["CONFIG_FILE"]]
    if env.get("EXTERNAL_CHECKS"):
        args += ["--external-checks-dir", env["EXTERNAL_CHECKS"]]
    return args


def main() -> int:
    env = dict(os.environ)
    out_dir = Path(env["OUT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)
    run = subprocess.run(command(env), text=True, encoding="utf-8")
    if run.returncode != 0:
        print(f"::error::checkov failed with exit code {run.returncode}.")
        return 1
    if not (out_dir / SARIF_NAME).is_file():
        print(f"::error::checkov left no {SARIF_NAME} in {out_dir}.")
        return 1
    print(f"checkov wrote {out_dir / SARIF_NAME}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
