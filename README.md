# Organisation repository for benethos-hub

[![CI](https://github.com/benethos-hub/.github/actions/workflows/ci.yml/badge.svg)](https://github.com/benethos-hub/.github/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benethos-hub/.github/badges/coverage.json&logo=githubactions&logoColor=white)](https://github.com/benethos-hub/.github/actions/workflows/ci.yml)
[![Brand report](https://github.com/benethos-hub/.github/actions/workflows/brand-report.yml/badge.svg)](https://github.com/benethos-hub/.github/actions/workflows/brand-report.yml)
[![Download pins report](https://github.com/benethos-hub/.github/actions/workflows/download-pins-report.yml/badge.svg)](https://github.com/benethos-hub/.github/actions/workflows/download-pins-report.yml)

[![Sponsor](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/sponsor.svg)](https://github.com/sponsors/BeneODev)
[![PayPal](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/paypal.svg)](https://paypal.me/BeneODev)

Organisation defaults for benethos-hub, and the CI and release process its repositories share. The organisation profile lives in [profile/README.md](profile/README.md).

The repositories call the workflows and actions here at `main`. A project needs no copy of any of it, and a rule changed here applies everywhere on the next run.

## Contents

| Path | What it holds |
| --- | --- |
| [.github/workflows/](.github/workflows/) | The reusable workflows, the two weekly reports and the CI of this repository |
| [actions/](actions/) | The composite actions: `brand/`, `python/`, `release/`, `publish/`, and `coverage-badge/` for every language |
| [.github/actions/](.github/actions/) | Actions the workflows of this repository use themselves |
| [.github/scripts/](.github/scripts/) | Scripts the workflows of this repository run themselves |
| [.github/dependabot.yml](.github/dependabot.yml) | Weekly updates for every pinned action and every lockfile here |
| [.github/download-pins.yml](.github/download-pins.yml) | Downloads pinned by version and checksum, which Dependabot cannot see |
| [docs/](docs/) | How the shared process works and how a repository adopts it, one page per topic |
| [tests/](tests/) | Tests for the scripts of the actions and for how the workflows wire them |
| [pyproject.toml](pyproject.toml), [uv.lock](uv.lock) | The tools for the checks of this repository, locked, with their settings |
| [FUNDING.yml](FUNDING.yml), [SECURITY.md](SECURITY.md), [profile/](profile/) | The organisation files, see the end of this page |

Workflows have to live directly in `.github/workflows`, because GitHub ignores subfolders there, so the ones for Python projects start with `python-`. Actions may live in subfolders. Each workflow and action names its call in its header comment, and each one that runs a script keeps that script next to it, tested in `tests/`.

## Documentation

| Page | What it covers |
| --- | --- |
| [Setting up a new repository](docs/new-repository.md) | The steps that give a new repository everything the existing ones have, in order |
| [CI of a Python project](docs/ci.md) | The `ci.yml` of a project, the reusable workflows and the names of their checks |
| [Badges](docs/badges.md) | The badge rows of every README, their colours and logos, and the coverage badge |
| [Publishing a release](docs/releases.md) | The `publish.yml` of a project, the publishing actions, the release gate, release tags, trial runs and the one-time setup |
| [Brand assets](docs/brand-assets.md) | The icon and social preview of every repository, the check in the CI and the weekly report |
| [Repository settings](docs/repository-settings.md) | The settings in GitHub: merging, branch protection, release tags, environments, security, Actions and Dependabot |
| [Maintaining this repository](docs/maintaining.md) | How a change here reaches the projects, the checks of this repository and its dependencies |

## Organisation files

GitHub applies these files to every repository of the organisation that has no file of its own. They are not part of the repositories themselves, so they are missing from clones and downloads.

| File | Purpose |
| --- | --- |
| [FUNDING.yml](FUNDING.yml) | Sponsor links shown on every repository |
| [SECURITY.md](SECURITY.md) | The security policy. A repository only needs its own if it has something specific to say, for example what counts as a vulnerability in that project. |
| [profile/README.md](profile/README.md) | The organisation profile shown on github.com/benethos-hub |

The security policy asks for private reports under Security, Report a vulnerability. That button only appears when private vulnerability reporting is enabled in the security settings of the repository. Every repository has it on, see [Repository settings](docs/repository-settings.md#security).
