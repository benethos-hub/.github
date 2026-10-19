"""Fail a release whose commit has no green CI run on the default branch.

A version on PyPI cannot be replaced, and nothing in the release itself runs
the tests. The release is cut from a merge commit on the default branch, and
the push of that commit ran the full CI: every required check, the whole matrix
and the audits. This waits for that run and passes only when it succeeded. A
commit that never reached the branch has no such run and stops the release as
well.

GITHUB_REPOSITORY and GITHUB_SHA come from the runner, GITHUB_TOKEN needs
actions: read. CI_WORKFLOW names the CI workflow file, CI_BRANCH the branch
whose push runs count, and CI_WAIT_MINUTES bounds the wait for a run still in
progress. The action next to this script sets all three.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

Fetch = Callable[[str], dict[str, Any]]


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result: dict[str, Any] = json.load(response)
        return result


def runs_url(
    repository: str,
    sha: str,
    workflow: str = "ci.yml",
    branch: str = "main",
    api: str = "https://api.github.com",
) -> str:
    """The API address that lists the push runs of ``workflow`` for ``sha``."""
    query = urllib.parse.urlencode(
        {"head_sha": sha, "event": "push", "branch": branch, "per_page": 10}
    )
    workflow_part = urllib.parse.quote(workflow, safe="")
    return f"{api}/repos/{repository}/actions/workflows/{workflow_part}/runs?{query}"


def check(
    repository: str,
    sha: str,
    workflow: str = "ci.yml",
    branch: str = "main",
    fetch: Fetch = fetch_json,
    wait_seconds: float = 1800,
    interval: float = 30,
    sleep: Callable[[float], None] = time.sleep,
    appear_seconds: float = 300,
    api: str = "https://api.github.com",
) -> int:
    """0 once the newest CI run of a push to ``branch`` for ``sha`` succeeded.

    A run still in progress is waited for up to ``wait_seconds``. A run that
    does not exist at all is given ``appear_seconds`` to show up, since a push
    lists its run within seconds and a commit that never reached the branch
    never gets one.
    """
    url = runs_url(repository, sha, workflow, branch, api)
    waited = 0.0
    while True:
        runs = fetch(url).get("workflow_runs", [])
        # The newest run for the commit. A re-run keeps its run and only
        # raises run_attempt, so a run created later is a new push.
        run = max(runs, key=lambda r: r["created_at"], default=None)
        if run is not None and run["status"] == "completed":
            if run["conclusion"] == "success":
                print(f"CI passed on {branch} for {sha[:7]}: {run['html_url']}")
                return 0
            print(
                f"::error::CI on {branch} ended {run['conclusion']} for {sha[:7]}: "
                f"{run['html_url']}. Fix it on {branch} and release from a green commit."
            )
            return 1
        if run is None and waited >= min(appear_seconds, wait_seconds):
            print(
                f"::error::No CI run on {branch} for {sha[:7]}. A release is cut "
                f"from a commit that went through a pull request into {branch}."
            )
            return 1
        if run is not None and waited >= wait_seconds:
            print(
                f"::error::CI on {branch} for {sha[:7]} is still {run['status']} "
                f"after {wait_seconds:.0f} s: {run['html_url']}"
            )
            return 1
        state = "no run yet" if run is None else run["status"]
        print(f"CI on {branch} for {sha[:7]}: {state}, checking again in {interval:.0f} s")
        sleep(interval)
        waited += interval


def main() -> int:
    workflow = os.environ.get("CI_WORKFLOW") or "ci.yml"
    branch = os.environ.get("CI_BRANCH", "")
    if not branch:
        print(
            "::error::No branch to look for the CI run on. Pass branch to the "
            "action, or run it on an event that names the default branch."
        )
        return 1
    try:
        return check(
            os.environ["GITHUB_REPOSITORY"],
            os.environ["GITHUB_SHA"],
            workflow,
            branch,
            wait_seconds=float(os.environ.get("CI_WAIT_MINUTES") or "30") * 60,
            api=os.environ.get("GITHUB_API_URL") or "https://api.github.com",
        )
    except urllib.error.HTTPError as error:
        print(
            f"::error::GitHub answered {error.code} when listing the runs of "
            f"{workflow}. Check that the workflow file exists and that the job "
            "grants actions: read."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
