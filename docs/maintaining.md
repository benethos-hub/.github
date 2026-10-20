# Maintaining this repository

## How a change reaches the projects

The repositories call every workflow and action here at `main`. A change merged here reaches all of them on their next run, without a pull request in any of them.

Some actions call others here at `main` as well: the three publishing actions call `release/tag-matches-version`, `python-release-ci-passed.yml` calls `release/ci-passed` and `python-dependency-audit.yml`, the audits call `python/pip-audit`, `python-tests.yml` calls `coverage-badge`, and `brand.yml` calls `brand/assets`. GitHub resolves such a call to `main` even in a pull request here, so a pull request cannot try a changed chain. The tests in `tests/` run the scripts and check the wiring, but the actions first run together after the merge. Only the workflows that `ci.yml` calls by local path are tried in a pull request, and the actions they call still come from `main`.

Two rules follow from that:

1. A change to an action and to the action that calls it lands in one commit, so `main` never holds one without the other.
2. After a change to a publishing action, try it in a project before its next release, through a manual run of its `publish.yml`.

## Checks of this repository

`ci.yml` checks this repository with its own `python-lint.yml`, `python-tests.yml`, `python-dependency-audit.yml` and `coverage-badge.yml`, called by local path, the way a project calls them. A job of its own checks the lockfiles of the actions. Ruff, pytest, pytest-cov, PyYAML and Mypy come from `uv.lock`, and their settings from `pyproject.toml`. The coverage covers the scripts the actions and workflows run.

The branch protection of `main` in this repository requires these checks. It binds admins as well, so every change reaches `main` through a pull request and passes these checks first, before any project loads it at `@main`:

- `lint / lint`
- `test / Python 3.11`, `test / Python 3.12`, `test / Python 3.13`, `test / Python 3.14` and `test / Python 3.15`
- `audit / Dependency audit`
- `Lockfiles of the actions`

The names come from the calling job and the job name in the called workflow. A change to either, or to the Python versions of `python-tests.yml`, changes the names, and the branch protection has to follow in the same step. Otherwise it waits for a check that never comes. `coverage-badge / Coverage badge` runs on a push only and is not required. The other settings of this repository are those of every repository, see [Repository settings](repository-settings.md).

## uv in the actions

The scripts of the actions run with `uv run --no-project --python ">=3.11"`, so they get the lowest Python this repository is checked against, whichever Python the runner brings. Every action that needs uv installs it itself, so a caller never has to. A second install in the same job comes from the runner's tool cache.

The uv cache in the GitHub Actions cache belongs to the job: no action saves it, and every workflow that does saves it under a key of its own, through `cache-suffix` or the Python version. `python-lowest-versions.yml` names its key after the Python version, `editable` and `requirements` of the call, so the calls of a repository with several packages do not share one. Jobs that run side by side would otherwise race for one key, and the loser would restore a cache another job filled.

A test in `tests/` fails for a script call without that version, for an action that saves the uv cache, for two workflows with the same cache key, for an action that uses another action without its folder in `dependabot.yml`, and for a lockfile without its folder there.

## Dependencies

Every action in a workflow or action here is pinned to a commit, with its version in a comment beside it. Dependabot raises commit and comment together. Every Python tool has its version in a `uv.lock` and every Node tool in a `package-lock.json`, never in a workflow. The pip-audit that `python/pip-audit` runs is locked next to the action, so the lockfile decides in every repository that uses it, and so is the packer of `publish/mcpb`. Dependabot keeps every lockfile current.

A tool downloaded directly, pinned by version and checksum like the `mcp-publisher` of `publish/mcp-registry`, is invisible to Dependabot. It gets an entry in [.github/download-pins.yml](../.github/download-pins.yml) instead. `download-pins-report.yml` checks every entry each Monday against the releases of its upstream and lists a newer release, with the version and checksum to paste, in the issue [Pinned downloads need an update](https://github.com/benethos-hub/.github/issues?q=is%3Aissue+%22Pinned+downloads+need+an+update%22).

Both weekly reports keep their issue through [.github/actions/report-issue](../.github/actions/report-issue/action.yml): one open issue per report, updated on every run and closed once nothing is left to report.
