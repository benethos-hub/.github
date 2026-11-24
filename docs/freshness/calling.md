# Freshness: calling it

Part of [FRESHNESS.md](../FRESHNESS.md).

## Calling it

The schedule, the run after a release, the concurrency group and the
permission to write issues belong to the calling repository:

```yaml
name: Freshness

on:
  schedule:
    - cron: "30 4 * * *"
  workflow_run:
    workflows: [Publish]
    types: [completed]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: freshness

jobs:
  freshness:
    uses: benethos-hub/.github/.github/workflows/freshness.yml@main
    permissions:
      contents: read
      issues: write
    with:
      issue-title: Pinned versions have newer releases
```

The `workflow_run` trigger runs it once more when the publishing
workflow has finished, named as its `name:` reads. The `index` job
installs the package from the index, so its answer changes at that
moment and at no other, and a release that does not install or does not
start shows in the alarm issue within minutes instead of at the next
schedule. The index can show a fresh version a minute late, then the run
measures the version before once and the schedule corrects it. A
publishing run that failed leaves the index as it was, so the run after
it repeats the day before. A repository without a publishing workflow
leaves the trigger out.

The weekly [CodeQL run](../CODEQL.md#calling-it) starts half an hour
later, at 05:00 UTC, so that the two do not fall together.

The concurrency group lets one run at a time. A second run waits and
starts when the first has finished, a third replaces the one waiting,
and the running one is never cancelled, so no report reads the artifacts
of another run and no two runs write the issue at once.

| Input | What it does |
| --- | --- |
| `issue-title` | The title of the issue. Required when the report is part of the call, without a default, because two workflows with the same title would keep the same issue and close or overwrite it for each other. An empty title with `report` on fails the run before anything is written. |
| `resolved` | The sentence that closes the issue when there is nothing to report. Default: `Every pin is current and nothing is known against it.` |
| `report` | Write the report at the end of this call. On by default. Off, the call only measures and gives the jobs it ran in its output `expected`, for a call of `freshness-report.yml` by the repository. |
| `ecosystem` | The package tool of the repository, named as Dependabot names it. Decides the adapter of the `outdated`, `audit` and `index` jobs. `uv` is the default and the only value so far. |
| `projects` | The folders with a lockfile of their own, as a JSON list in a string, such as `'[".", "tools/audit"]'`. The `outdated` and `audit` jobs run once per folder. The default is the root alone. See [Several projects in one repository](#several-projects-in-one-repository). |
| `outdated`, `audit`, `images`, `actions`, `index` | One switch per job. The first four are on by default, `index` is off. A job that is switched off is left out of the report. |
| `index-packages` | The distributions the `index` job installs, one run each, as a JSON list in a string, such as `'["example-mcp", "example-service"]'`. The default `'[""]'` is one run with the project in `pyproject.toml`, which a workspace root does not have. |
| `index-check` | The command the `index` job runs from the checkout against the installed package, with `FRESHNESS_PYTHON`, the interpreter of the environment, `FRESHNESS_VENV`, its folder, and `FRESHNESS_PACKAGE`, the package, set. For example `$FRESHNESS_PYTHON tests/smoke.py --pause 1`. Empty asks the console script named like the package for its version, or a library for its installed version. An exit code of 3 is a rate limit and no verdict, every other failure and a failed installation is a finding for the alarm issue. |
| `index-python` | The Python version of the environment the `index` job installs into. Empty takes the one uv picks. |
| `platforms` | The platforms a changed image digest counts for. Default `linux/amd64 linux/arm64`. A rebuild of another architecture moves the digest of the image as well and is nobody's news. |
| `image-files` | Patterns of the files the `images` job reads. Empty reads every `Dockerfile*` and every `yml` or `yaml` file of the repository, the workflows included, where the container or a service of a job is a pin like any other. |
| `action-files` | Patterns of the files the `actions` job reads. Empty reads the workflows and every `action.yml`. |
| `timeout-minutes` | The time each measuring job may take. Default 15. The report has 10 of its own. |
| `retention-days` | How long the findings of a run stay as artifacts, for a look at what the report was made of. Default 7. |
| `ignore` | Names of pins the repository keeps on purpose, as shell patterns, for example `example/server` for the image of a test server. Matching findings are dropped and counted. |
| `ignore-vulns` | Vulnerability IDs to waive, as in the CI. |
| `dev` | Show packages that are only needed in development. They are hidden and counted otherwise. |
| `transitive` | List transitive packages that moved by a minor, a patch or an unknown kind below the main tables, where they open the issue as well. Default true. false only counts them. |
| `extra-jobs` | Jobs of the calling workflow that leave an artifact for the report, separated by spaces. See [A job of the repository](repository-job.md#a-job-of-the-repository). |
| `alarm-title` | The title of a second issue for the jobs whose status names the alarm, the `index` job among them. Empty keeps everything in the one issue. |
| `alarm-resolved` | The sentence that closes the alarm issue when nothing is alarming any more. Default: `The checks pass again on the newest versions allowed.` |

The call has one output, `expected`: the measuring jobs of the call that
must have left an artifact, separated by spaces and with the suffix per
project and per package, such as
`outdated audit images actions index-example-mcp`. It is for a call of
`freshness-report.yml` by the repository and nothing else needs it.

The job names are `Which jobs must have a result`, `Outdated packages`,
`Known vulnerabilities`, `Container images`, `Pinned actions`,
`Installed from the index` and `Freshness report`. The second and third
carry the folder and the sixth the package in parentheses, as GitHub
names a run of a matrix, so the root shows as `Outdated packages (.)`.
The report appears beneath the job that calls it. None of them is a
required check, the workflow runs on a schedule.

## Workspaces

In a uv workspace the roots of the graph are the members in
`manifest.members` of the lockfile. The members themselves are never a
finding. `within_bounds` is measured for the resolution of the whole
workspace. A single package installed on its own with `uvx` sees only
its own bounds and can resolve differently. Build backends are read from
every `pyproject.toml`, not only the root.

## Several projects in one repository

A uv workspace is one project: one `uv.lock`, several packages. The
`outdated` and `audit` jobs read all of it, the report names the
packages a finding is needed by, and the `index` job runs once per
published package when `index-packages` names them. A library without a
console script shows its installed version as the default check, and
`index-check` can tell the packages apart through `FRESHNESS_PACKAGE`.

A repository with several independent lockfiles names their folders in
`projects`. The `outdated` and `audit` jobs run once per folder, each
with its own artifact, and the report shows the folder in `where`, as
`tools/audit/uv.lock`. A folder beneath a project with a lockfile of its
own belongs to its own run, so its build backend is counted once. The
`images` and `actions` jobs read the whole repository either way.

```yaml
    with:
      issue-title: Pinned versions have newer releases
      projects: '[".", "tools/audit"]'
      index: true
      index-packages: '["example-mcp", "example-service"]'
```

Each run leaves its own artifact, `freshness-outdated-tools-audit` or
`freshness-index-example-mcp`, and the report expects each of them. The
root and the one project keep the plain names, so nothing changes for a
repository that names neither.
