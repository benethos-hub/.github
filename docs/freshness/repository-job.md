# Freshness: a job of the repository

Part of [FRESHNESS.md](../FRESHNESS.md).

## A job of the repository

A repository adds a check of its own without a change here. A job of the calling workflow leaves an artifact `freshness-<job>` with the files of [FORMAT.md](../../actions/freshness/report/FORMAT.md): `status.json`, and `findings.jsonl` or `section.md` or both. The report learns of the job through `extra-jobs`, so a job that dies before its upload is a line in the issue and not a silent gap. The job runs beside the measuring jobs: `freshness.yml` is called with `report: false` and only measures, and `freshness-report.yml` is called after both, with the output `expected` of the measuring call.

```yaml
jobs:
  newest:
    name: Newest versions allowed
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha> # vX
      - name: Test on the newest versions the bounds allow
        run: ./newest.sh "$RUNNER_TEMP/freshness/newest"
      - uses: actions/upload-artifact@<sha> # vX
        with:
          name: freshness-newest
          path: ${{ runner.temp }}/freshness/newest

  measure:
    uses: benethos-hub/.github/.github/workflows/freshness.yml@main
    with:
      report: false

  report:
    needs: [newest, measure]
    if: ${{ !cancelled() }}
    uses: benethos-hub/.github/.github/workflows/freshness-report.yml@main
    permissions:
      contents: read
      issues: write
    with:
      issue-title: Pinned versions have newer releases
      expected: ${{ needs.measure.outputs.expected }}
      extra-jobs: newest
      alarm-title: Newest dependency versions break the server
```

`freshness-report.yml` takes `issue-title`, `resolved`, `extra-jobs`, `alarm-title`, `alarm-resolved`, `ignore`, `dev` and `transitive` with the meaning they have in [the call](calling.md#calling-it), and `expected`, the output of the measuring call. The permission to write issues goes to this call, the measuring call needs none. The `if` lets the report run when a job before it failed, which is then a line in the issue. Without it, GitHub skips the report after a failed job and the issue stays as it was. An empty `expected` fails the report before it writes anything: it means the output was lost or that nothing measured, and in both cases the issue has to stay as it was.

The one call works as well, with the job of the repository first and `needs` on the call. The report and the measuring jobs then wait for that job. Nothing else differs, both forms get the same artifacts, the same expected jobs and the same issue.

```yaml
  freshness:
    needs: newest
    if: ${{ !cancelled() }}
    uses: benethos-hub/.github/.github/workflows/freshness.yml@main
    permissions:
      contents: read
      issues: write
    with:
      issue-title: Pinned versions have newer releases
      extra-jobs: newest
      alarm-title: Newest dependency versions break the server
```

A job says in one sentence what it checked through `summary` in its status, such as which versions its tests passed on, and the report lists it under `Checks`. A job that says something alarming, such as tests that fail on the newest versions allowed, sets `"issue": "alarm"` in its status. Its findings and its section then go to the second issue named by `alarm-title`, and the pins report stays what it is. The alarm issue is touched only when every job was conclusive. A job that ran but could not prove anything, after a rate limit, say, sets `"result": "inconclusive"`: that is a line in the pins report, and the alarm issue is left as it was. Without `alarm-title` everything goes to the one issue.

For a uv project the job is ready made: [python/freshness-newest](../../actions/python/freshness-newest/action.yml) upgrades the lockfile inside the runner, runs the tests and an optional check on the newest versions allowed, after the same check on the locked ones, and leaves the artifact with `issue: alarm`, a summary of what passed and what moved, and a section when a step failed. A failure of the check on the locked versions, a rate limit or a failure without a move is inconclusive.

```yaml
  newest:
    name: Newest versions allowed
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha> # vX
      - uses: benethos-hub/.github/actions/python/freshness-newest@main
        with:
          findings: ${{ runner.temp }}/freshness/newest
          extras: dev
          check: uv run --frozen python tests/smoke.py --pause 1
      - uses: actions/upload-artifact@<sha> # vX
        with:
          name: freshness-newest
          path: ${{ runner.temp }}/freshness/newest
```

| Input of `freshness-newest` | What it does |
| --- | --- |
| `findings` | The folder for `status.json` and, on a failure, `section.md`. The upload step takes it from there. |
| `extras`, `groups` | The extras and dependency groups to sync, such as the one with the test tools. |
| `tests` | The command that runs the tests. Default `uv run --frozen pytest -q`. |
| `check` | A command run on the locked versions first and on the newest ones after, such as a smoke run against a live service. Empty runs the tests alone. |
| `rate-limit-exit-code` | The exit code of the check that means a rate limit and no verdict. Default 3. |
