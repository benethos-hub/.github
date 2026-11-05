# Freshness report

[freshness.yml](../.github/workflows/freshness.yml) tells a repository what it pins and what is newer, in one issue that stays open while there is something to report and closes when there is not. Five jobs measure, four of them by default:

| Job | What it measures |
| --- | --- |
| `outdated` | Every package the lockfile pins that has a newer release, how far it may move within the bounds the repository allows, and the newest release beyond them. Every build backend pinned to an exact version. |
| `audit` | Every known vulnerability of a pinned version, through the same [pip-audit](../actions/python/pip-audit/action.yml) action and the same waivers as the CI. |
| `images` | Every `FROM` of a Dockerfile and every `image:` of a YAML file with a digit in its tag, the workflows included. A pinned digest that moved for one of the platforms asked for is a rebuild. A tag with a newer tag of the same form, `3.15-slim` beside `3.16-slim` or `v0.16` beside `v0.17`, is a newer release. |
| `actions` | Every `uses:` pinned to a commit, against the newest release of its action. |
| `index` | Off by default. The package as a user installs it today: from the index into a fresh environment, then a check of the repository against it, with the interpreter of that environment. A bound that is not released yet, a build that fails or an installation that does not resolve shows here and nowhere else. Its result addresses the alarm issue. |

Nothing is written to the repository. The upgrade of the lockfile is a dry run inside the runner, and the environment of the `index` job lives in the runner's temporary folder. The issue is public, so the report holds names, versions and the result of a job, and no log.

The report is a workflow of its own, [freshness-report.yml](../.github/workflows/freshness-report.yml). `freshness.yml` calls it at the end of a run, so one call does everything. A repository with checks of its own calls the two apart, see [A job of the repository](#a-job-of-the-repository).

## Calling it

The schedule, the run after a release, the concurrency group and the permission to write issues belong to the calling repository:

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

The `workflow_run` trigger runs it once more when the publishing workflow has finished, named as its `name:` reads. The `index` job installs the package from the index, so its answer changes at that moment and at no other, and a release that does not install or does not start shows in the alarm issue within minutes instead of at the next schedule. The index can show a fresh version a minute late, then the run measures the version before once and the schedule corrects it. A publishing run that failed leaves the index as it was, so the run after it repeats the day before. A repository without a publishing workflow leaves the trigger out.

The concurrency group lets one run at a time. A second run waits and starts when the first has finished, a third replaces the one waiting, and the running one is never cancelled, so no report reads the artifacts of another run and no two runs write the issue at once.

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
| `extra-jobs` | Jobs of the calling workflow that leave an artifact for the report, separated by spaces. See [A job of the repository](#a-job-of-the-repository). |
| `alarm-title` | The title of a second issue for the jobs whose status names the alarm, the `index` job among them. Empty keeps everything in the one issue. |
| `alarm-resolved` | The sentence that closes the alarm issue when nothing is alarming any more. Default: `The checks pass again on the newest versions allowed.` |

The call has one output, `expected`: the measuring jobs of the call that must have left an artifact, separated by spaces and with the suffix per project and per package, such as `outdated audit images actions index-example-mcp`. It is for a call of `freshness-report.yml` by the repository and nothing else needs it.

The job names are `Which jobs must have a result`, `Outdated packages`, `Known vulnerabilities`, `Container images`, `Pinned actions`, `Installed from the index` and `Freshness report`. The second and third carry the folder and the sixth the package in parentheses, as GitHub names a run of a matrix, so the root shows as `Outdated packages (.)`. The report appears beneath the job that calls it. None of them is a required check, the workflow runs on a schedule.

## What the report says

Named one by one: every vulnerability, image and action, every build backend, every direct runtime package and every major of a runtime package. Only counted: transitive runtime packages that moved by a minor, a patch or an unknown kind. There are about as many of those as days, and the issue would never close. Development packages are hidden and counted unless `dev` is set. A repository with more than one package gets a column that names the packages each finding is needed by.

The kind of a finding is derived from its versions. A different first number is a major, a different second number a minor, any other difference a patch. A version that looks like a date is `unknown`, so a new `2026.5.4` never reads as a minor. A moved digest is a `rebuild`. The report says under its tables what is measured, the versions, and what is derived, the kind, the scope and the counts.

After the tables, a block `Checks` lists one sentence per job that has one, such as which versions a check passed on, so the issue that names a newer pandas also says that the tests passed on it the same day. Then the prose of the jobs that left some, each under a heading with the name of the job.

A job that fails is a line in the report, so a run that proved nothing never closes an open issue. A job that is switched off is not. The rules in full are in [FORMAT.md](../actions/freshness/report/FORMAT.md).

## What it leaves out

- A pin that floats on purpose: a tag without digits such as `caddy:2`, a tag built from a variable, a reference to `main` or to a version tag of an action, an unpinned build backend such as `hatchling` without a version. The `images` job still compares a floating tag with digits against newer tags of its form, so `caddy:2` learns of a `3`.
- A pin the caller names in `ignore`.
- A lockfile of a package tool without an adapter, such as `package-lock.json`. The `outdated` and `audit` jobs read the `uv.lock` of each folder in `projects` and fail with a word when there is none.

Dependabot covers part of this, the direct packages of the lockfile, the actions and the images of the Dockerfiles it is pointed at. The report adds the packages beneath them, the versions beyond the bounds, the build backends, the images of every YAML file, the rebuild per platform and the one place to see all of it. It opens no pull request.

## Workspaces

In a uv workspace the roots of the graph are the members in `manifest.members` of the lockfile. The members themselves are never a finding. `within_bounds` is measured for the resolution of the whole workspace. A single package installed on its own with `uvx` sees only its own bounds and can resolve differently. Build backends are read from every `pyproject.toml`, not only the root.

## Several projects in one repository

A uv workspace is one project: one `uv.lock`, several packages. The `outdated` and `audit` jobs read all of it, the report names the packages a finding is needed by, and the `index` job runs once per published package when `index-packages` names them. A library without a console script shows its installed version as the default check, and `index-check` can tell the packages apart through `FRESHNESS_PACKAGE`.

A repository with several independent lockfiles names their folders in `projects`. The `outdated` and `audit` jobs run once per folder, each with its own artifact, and the report shows the folder in `where`, as `tools/audit/uv.lock`. A folder beneath a project with a lockfile of its own belongs to its own run, so its build backend is counted once. The `images` and `actions` jobs read the whole repository either way.

```yaml
    with:
      issue-title: Pinned versions have newer releases
      projects: '[".", "tools/audit"]'
      index: true
      index-packages: '["example-mcp", "example-service"]'
```

Each run leaves its own artifact, `freshness-outdated-tools-audit` or `freshness-index-example-mcp`, and the report expects each of them. The root and the one project keep the plain names, so nothing changes for a repository that names neither.

## A job of the repository

A repository adds a check of its own without a change here. A job of the calling workflow leaves an artifact `freshness-<job>` with the files of [FORMAT.md](../actions/freshness/report/FORMAT.md): `status.json`, and `findings.jsonl` or `section.md` or both. The report learns of the job through `extra-jobs`, so a job that dies before its upload is a line in the issue and not a silent gap. The job runs beside the measuring jobs: `freshness.yml` is called with `report: false` and only measures, and `freshness-report.yml` is called after both, with the output `expected` of the measuring call.

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

`freshness-report.yml` takes `issue-title`, `resolved`, `extra-jobs`, `alarm-title`, `alarm-resolved`, `ignore` and `dev` with the meaning above, and `expected`, the output of the measuring call. The permission to write issues goes to this call, the measuring call needs none. The `if` lets the report run when a job before it failed, which is then a line in the issue. Without it, GitHub skips the report after a failed job and the issue stays as it was. An empty `expected` fails the report before it writes anything: it means the output was lost or that nothing measured, and in both cases the issue has to stay as it was.

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

For a uv project the job is ready made: [python/freshness-newest](../actions/python/freshness-newest/action.yml) upgrades the lockfile inside the runner, runs the tests and an optional check on the newest versions allowed, after the same check on the locked ones, and leaves the artifact with `issue: alarm`, a summary of what passed and what moved, and a section when a step failed. A failure of the check on the locked versions, a rate limit or a failure without a move is inconclusive.

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

## Another language

The jobs `images`, `actions` and the report know no language. The jobs `outdated`, `audit` and `index` run one step per ecosystem, guarded by `if: inputs.ecosystem == 'uv'`, and fail with a word for an ecosystem without a step. A second language adds an adapter action that writes the files [FORMAT.md](../actions/freshness/report/FORMAT.md) describes, and one such step per job. The report needs no change.

The actions behind the jobs, each usable on its own:

| Action | Knows |
| --- | --- |
| [python/freshness-outdated](../actions/python/freshness-outdated/action.yml) | `uv.lock`, `pyproject.toml`, `uv lock --upgrade --dry-run` and `uv tree --outdated --universal`, in the folder named by `directory` |
| [python/freshness-audit](../actions/python/freshness-audit/action.yml) | `uv export` in the folder named by `directory` and the pip-audit action with `findings` |
| [python/freshness-index](../actions/python/freshness-index/action.yml) | `uv venv`, `uv pip install` from the index, `uv pip freeze` and the check of the repository |
| [python/freshness-newest](../actions/python/freshness-newest/action.yml) | `uv lock --upgrade` in the runner, `uv sync`, the tests and the check of the repository. A job of the repository, not of the workflow. |
| [freshness/images](../actions/freshness/images/action.yml) | Dockerfiles, YAML files and the registry API, read anonymously as `docker pull` does |
| [freshness/actions](../actions/freshness/actions/action.yml) | `uses:` lines and the GitHub API |
| [freshness/report](../actions/freshness/report/action.yml) | Only the files per job |

The registry of Docker Hub counts anonymous reads against the address of the runner, which is shared. A run asks it for one or two manifests, which has been enough so far.
