"""Run the misconfiguration scan of Trivy over the checkout and leave a SARIF file.

Environment: TRIVY names the binary, SCAN_PATH the folder, SCANNERS the
misconfiguration scanners, SEVERITY the severities, SKIP_DIRS and SKIP_FILES
the patterns to leave out, IGNOREFILE a .trivyignore, CONFIG a trivy.yaml,
CHECKS folders of custom checks, NAMESPACES their Rego namespaces, OFFLINE
true to skip the update of the checks, CACHE_DIR where Trivy caches, OUT the
SARIF file to write. Each is passed through unchanged, empty means Trivy's
default. The exit code is 0 whatever is found, the verdict is the report's.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FLAGS = {
    "SCANNERS": "--misconfig-scanners",
    "SEVERITY": "--severity",
    "SKIP_DIRS": "--skip-dirs",
    "SKIP_FILES": "--skip-files",
    "IGNOREFILE": "--ignorefile",
    "CONFIG": "--config",
    "CHECKS": "--config-check",
    "NAMESPACES": "--check-namespaces",
}


def command(env: dict[str, str]) -> list[str]:
    """The trivy call from the environment."""
    args = [
        env.get("TRIVY") or "trivy",
        "config",
        "--quiet",
        "--format",
        "sarif",
        "--output",
        env["OUT"],
        "--exit-code",
        "0",
    ]
    if env.get("CACHE_DIR"):
        args += ["--cache-dir", env["CACHE_DIR"]]
    for key, flag in FLAGS.items():
        value = env.get(key, "").strip()
        if value:
            args += [flag, ",".join(value.split())]
    if env.get("OFFLINE", "").lower() == "true":
        args.append("--skip-check-update")
    return [*args, env.get("SCAN_PATH") or "."]


def main() -> int:
    env = dict(os.environ)
    out = Path(env["OUT"])
    out.parent.mkdir(parents=True, exist_ok=True)
    run = subprocess.run(command(env), text=True, encoding="utf-8")
    if run.returncode != 0:
        print(f"::error::trivy failed with exit code {run.returncode}.")
        return 1
    if not out.is_file():
        print(f"::error::trivy left no {out}.")
        return 1
    print(f"trivy wrote {out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
