# Freshness report

[freshness.yml](../.github/workflows/freshness.yml) tells a repository what it pins and what is newer, in one issue that stays open while there is something to report and closes when there is not. Five jobs measure, four of them by default:

| Job | What it measures |
| --- | --- |
| `outdated` | Every package the lockfile pins that has a newer release, how far it may move within the bounds the repository allows, and the newest release beyond them. Every build backend pinned to an exact version. |
| `audit` | Every known vulnerability of a pinned version, through the same [pip-audit](../actions/python/pip-audit/action.yml) action and the same waivers as the CI. |
| `images` | Every `FROM` of a Dockerfile and every `image:` of a YAML file with a digit in its tag, the workflows included. A pinned digest that moved for one of the platforms asked for is a rebuild. A tag with a newer tag of the same form, `3.15-slim` beside `3.16-slim` or `v0.16` beside `v0.17`, is a newer release. |
| `actions` | Every `uses:` pinned to a commit, against the newest release of its action. A latest release whose tag is no version, such as the CodeQL bundle of `github/codeql-action`, counts for nothing, and the highest version among its releases takes its place. |
| `index` | Off by default. The package as a user installs it today: from the index into a fresh environment, then a check of the repository against it, with the interpreter of that environment. A bound that is not released yet, a build that fails or an installation that does not resolve shows here and nowhere else. Its result addresses the alarm issue. |

Nothing is written to the repository. The upgrade of the lockfile is a dry run inside the runner, and the environment of the `index` job lives in the runner's temporary folder. The issue is public, so the report holds names, versions and the result of a job, and no log.

The report is a workflow of its own, [freshness-report.yml](../.github/workflows/freshness-report.yml). `freshness.yml` calls it at the end of a run, so one call does everything. A repository with checks of its own calls the two apart, see [A job of the repository](freshness/repository-job.md#a-job-of-the-repository).

This file is the overview. It holds what the jobs measure, what the report says and what it leaves out. The rest is in [freshness/](freshness/).

## The topics

| Topic | In short |
| --- | --- |
| [Calling it](freshness/calling.md) | The call with its schedule, every input, the output, the job names, workspaces and several projects in one repository. |
| [A job of the repository](freshness/repository-job.md) | A check of the repository's own in the same report, the alarm issue, and the ready-made job for the newest versions a uv project allows. |
| [A package-lock.json](freshness/npm.md) | The two actions that measure a lockfile of npm, called as jobs of the repository. |
| [Another language](freshness/other-languages.md) | How a second language joins, and the actions behind the jobs. |

## What the report says

Named one by one: every vulnerability, image and action, every build backend, every direct runtime package and every major of a runtime package. Listed below them, in a table of their own: transitive runtime packages that moved by a minor, a patch or an unknown kind. They open the issue as well, since Dependabot proposes direct dependencies only, and the issue stays open until a refresh of the lockfile takes them. There are about as many of them as days. A repository that wants them only counted sets `transitive: false`. Development packages are hidden and counted unless `dev` is set. A repository with more than one package gets a column that names the packages each finding is needed by.

The kind of a finding is derived from its versions. A different first number is a major, a different second number a minor, any other difference a patch. A version that looks like a date is `unknown`, so a new `2026.5.4` never reads as a minor. A moved digest is a `rebuild`. The report says under its tables what is measured, the versions, and what is derived, the kind, the scope and the counts.

After the tables, a block `Checks` lists one sentence per job that has one, such as which versions a check passed on, so the issue that names a newer pandas also says that the tests passed on it the same day. A passed check starts with ✅. A job of the alarm issue that found something gets ❌ and a pointer to its section. A job that failed or left no result is a line with ❌, a job that could not prove anything one with ⚠️. Then the prose of the jobs that left some, each under a heading with the name of the job.

A job that fails is a line in the report, so a run that proved nothing never closes an open issue. A job that is switched off is not. The rules in full are in [FORMAT.md](../actions/freshness/report/FORMAT.md).

## What it leaves out

- A pin that floats on purpose: a tag without digits such as `caddy:2`, a tag built from a variable, a reference to `main` or to a version tag of an action, an unpinned build backend such as `hatchling` without a version. The `images` job still compares a floating tag with digits against newer tags of its form, so `caddy:2` learns of a `3`.
- A pin the caller names in `ignore`.
- A lockfile other than `uv.lock` in the jobs of the workflow. The `outdated` and `audit` jobs read the `uv.lock` of each folder in `projects` and fail with a word when there is none. A `package-lock.json` is measured by two actions a repository calls as jobs of its own, see [A package-lock.json](freshness/npm.md#a-package-lockjson).

Dependabot covers part of this, the direct packages of the lockfile, the actions and the images of the Dockerfiles it is pointed at. The report adds the packages beneath them, the versions beyond the bounds, the build backends, the images of every YAML file, the rebuild per platform and the one place to see all of it. It opens no pull request.
