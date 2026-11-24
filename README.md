# Organisation repository for benethos-hub

[![CI](https://github.com/benethos-hub/.github/actions/workflows/ci.yml/badge.svg)](https://github.com/benethos-hub/.github/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benethos-hub/.github/badges/coverage.json&logo=githubactions&logoColor=white)](https://github.com/benethos-hub/.github/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/benethos-hub/.github?logo=opensourceinitiative&logoColor=white)](https://github.com/benethos-hub/.github/blob/main/LICENSE)
[![Brand report](https://github.com/benethos-hub/.github/actions/workflows/brand-report.yml/badge.svg)](https://github.com/benethos-hub/.github/actions/workflows/brand-report.yml)
[![Download pins report](https://github.com/benethos-hub/.github/actions/workflows/download-pins-report.yml/badge.svg)](https://github.com/benethos-hub/.github/actions/workflows/download-pins-report.yml)

[![Sponsor](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/sponsor.svg)](https://github.com/sponsors/BeneODev)
[![PayPal](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/paypal.svg)](https://paypal.me/BeneODev)

Organisation defaults for benethos-hub, and the CI and release process its repositories share. The organisation profile lives in [profile/README.md](profile/README.md).

The repositories call the workflows and actions here at `main`. A project needs no copy of any of it, and a rule changed here applies everywhere on the next run.

**Contents**

- [What it holds](#what-it-holds)
- [Documentation](#documentation)
- [Organisation files](#organisation-files)

## What it holds

| Path | What it holds |
| --- | --- |
| [.github/workflows/](.github/workflows/) | The reusable workflows, the two weekly reports and the CI of this repository |
| [actions/](actions/) | The composite actions: `brand/`, `node/`, `python/`, `release/`, `publish/`, and `checkov/`, `codeql/`, `coverage-badge/`, `dockerfile-lint/`, `freshness/`, `report-issue/`, `sarif-report/` and `trivy-config/` for every language |
| [.github/scripts/](.github/scripts/) | Scripts the workflows of this repository run themselves |
| [.github/dependabot.yml](.github/dependabot.yml) | Daily updates for every pinned action and every lockfile here |
| [.github/download-pins.yml](.github/download-pins.yml) | Downloads pinned by version and checksum, which Dependabot cannot see |
| [docs/](docs/) | How the shared process works and how a repository adopts it, one page per topic |
| [tests/](tests/) | Tests for the scripts of the actions and for how the workflows wire them |
| [pyproject.toml](pyproject.toml), [uv.lock](uv.lock) | The tools for the checks of this repository, locked, with their settings |
| [FUNDING.yml](FUNDING.yml), [SECURITY.md](SECURITY.md), [profile/](profile/) | The organisation files, see the end of this page |

Workflows have to live directly in `.github/workflows`, because GitHub ignores subfolders there, so the ones for Python projects start with `python-`. Actions may live in subfolders. Each workflow and action names its call in its header comment, and each one that runs a script keeps that script next to it, tested in `tests/`.

## Documentation

- [docs/README.md](docs/README.md): every document, by topic
- [docs/NEW-REPOSITORY.md](docs/NEW-REPOSITORY.md): the steps that give a new repository everything the existing ones have, in order
- [docs/REPOSITORY-SETTINGS.md](docs/REPOSITORY-SETTINGS.md): the settings in GitHub, from merging to Dependabot
- [docs/CI.md](docs/CI.md): the `ci.yml` of a Python project, the reusable workflows and the names of their checks
- [docs/CODEQL.md](docs/CODEQL.md): the CodeQL analysis as a job of the CI and on a schedule
- [docs/DOCKERFILE-CHECKS.md](docs/DOCKERFILE-CHECKS.md): hadolint, Trivy and Checkov over the Dockerfiles
- [docs/BADGES.md](docs/BADGES.md): the badge rows of every README and the coverage badge
- [docs/BRAND-ASSETS.md](docs/BRAND-ASSETS.md): the icon and social preview of every repository
- [docs/RELEASES.md](docs/RELEASES.md): the `publish.yml` of a project, the release gate and release tags
- [docs/REPORTS.md](docs/REPORTS.md): how a scheduled workflow keeps its result in one issue
- [docs/FRESHNESS.md](docs/FRESHNESS.md): the daily report of what a repository pins and what is newer
- [docs/MCP-SERVER-STATUS.md](docs/MCP-SERVER-STATUS.md): the status tool every MCP server of the organisation offers
- [docs/MAINTAINING.md](docs/MAINTAINING.md): how a change here reaches the projects, the checks and dependencies of this repository

## Organisation files

GitHub applies these files to every repository of the organisation that has no file of its own. They are not part of the repositories themselves, so they are missing from clones and downloads.

| File | Purpose |
| --- | --- |
| [FUNDING.yml](FUNDING.yml) | Sponsor links shown on every repository |
| [SECURITY.md](SECURITY.md) | The security policy. A repository only needs its own if it has something specific to say, for example what counts as a vulnerability in that project. |
| [profile/README.md](profile/README.md) | The organisation profile shown on github.com/benethos-hub |

The security policy asks for private reports under Security, Report a vulnerability. That button only appears when private vulnerability reporting is enabled in the security settings of the repository. Every repository has it on, see [Repository settings](docs/REPOSITORY-SETTINGS.md#security).
