# .github

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
| [tests/](tests/) | Tests for the scripts of the actions and for how the workflows wire them |
| [pyproject.toml](pyproject.toml), [uv.lock](uv.lock) | The tools for the checks of this repository, locked, with their settings |
| [FUNDING.yml](FUNDING.yml), [SECURITY.md](SECURITY.md), [profile/](profile/) | The organisation files, see the end of this page |

Workflows have to live directly in `.github/workflows`, because GitHub ignores subfolders there, so the ones for Python projects start with `python-`. Actions may live in subfolders. Each workflow and action names its call in its header comment, and each one that runs a script keeps that script next to it, tested in `tests/`.

## CI of a Python project

A Python project managed with uv calls these workflows from its `ci.yml`:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  brand:
    uses: benethos-hub/.github/.github/workflows/brand.yml@main

  lint:
    uses: benethos-hub/.github/.github/workflows/python-lint.yml@main
    with:
      sync-args: --extra dev

  test:
    uses: benethos-hub/.github/.github/workflows/python-tests.yml@main
    with:
      sync-args: --extra dev
      cov: benethos_example
      badge: true

  lowest-versions:
    uses: benethos-hub/.github/.github/workflows/python-lowest-versions.yml@main
    with:
      requirements: pytest>=9.1.1
      audit: true

  audit:
    uses: benethos-hub/.github/.github/workflows/python-dependency-audit.yml@main

  coverage-badge:
    if: github.event_name == 'push'
    needs: test
    uses: benethos-hub/.github/.github/workflows/coverage-badge.yml@main
    permissions:
      contents: write
```

| Workflow | What it checks | Inputs |
| --- | --- | --- |
| [brand.yml](.github/workflows/brand.yml) | The brand assets, see [Brand assets](#brand-assets) | none |
| [python-lint.yml](.github/workflows/python-lint.yml) | `uv.lock` in step with `pyproject.toml`, Ruff lint and format, Mypy. The tools and their settings come from the project. | `sync-args`, `timeout-minutes` |
| [python-tests.yml](.github/workflows/python-tests.yml) | pytest on every supported Python against `uv.lock`. The newest version also measures the coverage and enforces its floor, 80 % by default. | `python-versions`, `coverage-python`, `sync-args`, `cov`, `cov-fail-under`, `badge`, `timeout-minutes` |
| [python-lowest-versions.yml](.github/workflows/python-lowest-versions.yml) | The tests against the lowest versions `pyproject.toml` allows, on the oldest supported Python, without the lockfile. With `audit: true`, those versions are audited too. | `python-version`, `editable`, `requirements`, `pytest-args`, `audit`, `ignore-vulns`, `timeout-minutes` |
| [python-dependency-audit.yml](.github/workflows/python-dependency-audit.yml) | Every version pinned in `uv.lock`, for every platform and Python, against PyPI and OSV. A vulnerability without a fix is waived by ID. | `ignore-vulns` |
| [coverage-badge.yml](.github/workflows/coverage-badge.yml) | Nothing. It publishes the coverage badge, of any language, see [Coverage badge](#coverage-badge). | `artifact`, `branch` |

The checks are named after the calling job and the job inside the workflow: `lint / lint`, `test / Python 3.15`, `lowest-versions / Python 3.11`, `audit / Dependency audit` and `brand / Brand assets`. These are the names a branch ruleset requires. A project names its Python versions in `with:` even where they equal the defaults, so that a changed default here never moves its tests without a word.

Coverage is measured on one version only, because it slows the older ones down noticeably. A required check on `test / Python 3.15` is what makes the floor block a merge.

### Badges

The README of every repository opens with its badges, right after the title, in three rows, or more for a repository with several packages. A blank line between the rows keeps them apart.

The first row says whether the project is in order and what it runs on:

1. CI, the status badge of `ci.yml`
2. Coverage, from the `badges` branch, see below. Only where the tests measure it.
3. License, read by shields.io from the `LICENSE` file. Only where the repository has one.
4. The language versions the project supports, read from where the project declares them.

The second row says where to get it: one badge per package on its registry and one container badge per image. A repository that publishes nothing has no second row.

A repository with several packages, such as a uv workspace, gives each package a row of its own instead. The packages people run come first and the libraries they build on last, in mailbox for example service, mcp, client and common. Each row holds the badge of the package on its registry first and, where the package has an image, its container badge after it. A blank line separates these rows as well, since GitHub shows lines without one in a single row. The sponsor row follows after the last package.

The third row holds the sponsor links, GitHub Sponsors and PayPal. The badges are served from [profile/badges](profile/badges/) in this repository, the same files the organisation profile shows, so every repository carries the same two and a change here reaches all of them.

None of the badges carries a value written by hand, and all of them use the default style of shields.io. The colours are the same in every repository, and each one means something. The CI badge is green or red, as GitHub draws it. The coverage badge follows the usual scale, green from 80, bright green from 90 and red below 50. The licence badge keeps the colour shields.io gives the licence, green for a permissive one such as MIT and orange for copyleft. A version badge keeps the colour shields.io gives the version, orange below 1.0 and blue from 1.0 on, so a package before its first stable release is visible as such. The badge of the supported language versions is blue, with `color=blue` where shields.io would choose otherwise. The container badge carries the Docker blue `2496ED`. The sponsor badges keep the colours of their files.

Every badge of the first two rows carries a white logo from [simple-icons](https://simpleicons.org/), through `logo=<name>&logoColor=white`: the licence the Open Source Initiative, the language versions the language, the package its registry, the container Docker, and the coverage GitHub Actions, where it is measured, for every language. The CI badge brings its GitHub mark itself, and the sponsor badges have theirs in their files.

```markdown
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/<owner>/<repo>/badges/coverage.json&logo=githubactions&logoColor=white)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/<owner>/<repo>?logo=opensourceinitiative&logoColor=white)](https://github.com/<owner>/<repo>/blob/main/LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/<package>?logo=python&logoColor=white)](https://pypi.org/project/<package>/)

[![PyPI <package>](https://img.shields.io/pypi/v/<package>?label=PyPI%20<package>&logo=pypi&logoColor=white)](https://pypi.org/project/<package>/)
[![Container <image>](https://img.shields.io/badge/ghcr.io-<image>-2496ED?logo=docker&logoColor=white)](https://github.com/<owner>/<repo>/pkgs/container/<image>)

[![Sponsor](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/sponsor.svg)](https://github.com/sponsors/BeneODev)
[![PayPal](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/paypal.svg)](https://paypal.me/BeneODev)
```

In the container badge, a dash in the image name is written as `--`, since shields.io reads a single dash as the separator.

The example is a Python project. The rule is the same for every language, only the two badges that read a package differ:

| Language | Versions, first row | Package, second row |
| --- | --- | --- |
| Python | `pypi/pyversions/<package>?logo=python` | `pypi/v/<package>?label=PyPI%20<package>&logo=pypi` |
| Go | `github/go-mod/go-version/<owner>/<repo>?logo=go` | `github/v/release/<owner>/<repo>?label=Release&logo=github`, since a module is fetched from the repository |
| Node | `node/v/<package>?logo=nodedotjs&color=blue` | `npm/v/<package>?label=npm%20<package>&logo=npm` |

Each is a path under `https://img.shields.io/`, with `&logoColor=white` added. The version badges keep the colour of shields.io, the Node versions badge would be green without `color=blue`.

This repository has no licence file and publishes nothing. Its first row at the top of this page goes on with the two weekly reports instead, which are status badges as well, and its second row is missing.

#### Coverage badge

With `badge: true`, `python-tests.yml` reads the measured percentage and hands it to the action `coverage-badge`, which writes the JSON of a [shields.io endpoint badge](https://shields.io/badges/endpoint-badge), uploaded as the artifact `coverage-badge`. `coverage-badge.yml` then commits that file as `coverage.json` on the `badges` branch of the repository, which it creates on the first run. The branch carries nothing else, and the job needs `contents: write` for the push. Call it on a push to the default branch only, so the badge shows the coverage of that branch, and never make it a required check, since a pull request does not run it.

Only the measuring step knows the language. The action takes a percentage, and the workflow takes a file, so a project in another language brings a test workflow of its own that reads its coverage and calls the same two. The percentage is rounded down, so a badge at the floor means the floor holds. After the first push to the default branch, the badge can show "resource not found" for a few minutes: the README is online before the job has created the branch, and GitHub and shields.io cache that first answer. It corrects itself.

## Publishing a release

A release is published from the `publish.yml` of a project on the event `release`. Every upload is done by an action here. They are composite actions and not reusable workflows on purpose: PyPI's Trusted Publishing and the MCP Registry identify the workflow of the job that uploads, so that job has to stay in the project.

```yaml
on:
  release:
    types: [published]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  ci-passed:
    if: github.event_name == 'release' || github.ref == 'refs/heads/main'
    uses: benethos-hub/.github/.github/workflows/python-release-ci-passed.yml@main
    permissions:
      actions: read
      contents: read
    with:
      audit: true

  pypi-publish:
    if: github.event_name == 'release'
    needs: ci-passed
    runs-on: ubuntu-latest
    environment:
      name: pypi-benethos-example
      url: https://pypi.org/p/benethos-example
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@<sha> # vX
      - uses: benethos-hub/.github/actions/publish/pypi@main
        with:
          wheel-contains: benethos_example/py.typed

  pypi-trial:
    if: github.event_name == 'workflow_dispatch'
    needs: ci-passed
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<sha> # vX
      - uses: benethos-hub/.github/actions/publish/pypi@main
        with:
          dry-run: true
          wheel-contains: benethos_example/py.typed

  ghcr-publish:
    if: github.event_name == 'release' || github.ref == 'refs/heads/main'
    needs: ci-passed
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@<sha> # vX
      - uses: benethos-hub/.github/actions/publish/ghcr@main
        with:
          image: benethos-example
          dockerfile: containers/images/example/Dockerfile

  mcpb-bundle:
    if: github.event_name == 'release'
    needs: ci-passed
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@<sha> # vX
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<sha> # vX
      - run: uv run --no-project .github/publish/mcpb/build.py "$RUNNER_TEMP/bundle"
      - uses: benethos-hub/.github/actions/publish/mcpb@main
        with:
          staged: ${{ runner.temp }}/bundle
          name: benethos-example

  mcp-registry:
    if: github.event_name == 'release' && !github.event.release.prerelease
    needs: [pypi-publish, ghcr-publish, mcpb-bundle]
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@<sha> # vX
      - uses: benethos-hub/.github/actions/publish/mcp-registry@main
```

| Action | What it does | Inputs |
| --- | --- | --- |
| [release/ci-passed](actions/release/ci-passed/action.yml) | Waits for the CI run of the released commit on the default branch and fails unless it succeeded. Used through `python-release-ci-passed.yml`. | `workflow`, `branch`, `wait-minutes`, `token` |
| [release/tag-matches-version](actions/release/tag-matches-version/action.yml) | Fails unless the release tag is the version in a `pyproject.toml` or a JSON file such as `manifest.json` or `server.json`. The publishing actions run it first. | `file`, `tag` |
| [publish/pypi](actions/publish/pypi/action.yml) | Builds sdist and wheel with uv, checks that the wheel is the package asked for, carries the version of the tag and every path in `wheel-contains`, and uploads through Trusted Publishing. A file already on PyPI with the same content is skipped, so a failed upload can be run again. In a uv workspace, `package` names the member, one job per member. | `package`, `wheel-contains`, `tag`, `dry-run` |
| [publish/ghcr](actions/publish/ghcr/action.yml) | Builds a multi-arch image and pushes it to ghcr.io as `1.2.3`, `1.2` and `latest`, or `edge` from a manual run. Then reads the published index back: every tag the same index, with description, source, version and every platform. One image per call, a repository with several images uses a matrix. Each image keeps its own build cache. `cache-scope` names the scope a CI build of the same image writes to, so the release reuses its layers. | `image`, `dockerfile`, `context`, `platforms`, `description`, `version-scheme`, `version-file`, `cache-scope`, `token` |
| [publish/mcpb](actions/publish/mcpb/action.yml) | Takes a staged Claude Desktop bundle, checks its version, validates and packs it, holds the packed file to the staged tree byte for byte, and attaches it to the release as `<name>-1.2.3.mcpb` and `<name>.mcpb`. The packer is locked in `package-lock.json` next to the action. | `staged`, `name`, `tag`, `token` |
| [publish/mcp-registry](actions/publish/mcp-registry/action.yml) | Publishes a `server.json` to the MCP Registry: checks its version, fills in the checksum of the bundle on the release, logs in with the workflow's OIDC token, retries a refusal and falls back to the entry without the bundle. `mcp-publisher` is pinned here for all repositories. | `entry`, `tag`, `attempts`, `wait-seconds`, `token` |

### The release gate

A version on PyPI cannot be replaced. `python-release-ci-passed.yml` therefore lets a release through only when the push of the release commit to the default branch ran `ci.yml` and that run succeeded. It waits up to 30 minutes for a run still in progress. A commit that never reached the default branch has no such run, and the gate stops the release after five minutes. The calling job grants `actions: read`, because a reusable workflow never gets more rights than its caller.

The calling job runs only for a release or on the default branch, through `if: github.event_name == 'release' || github.ref == 'refs/heads/main'`. A manual run on another branch then skips the gate and every job after it, instead of failing after five minutes although nothing broke. The condition stays in the calling job and not in the reusable workflow, because GitHub does not rate a calling job whose called jobs were all skipped reliably for `needs`.

With `audit: true`, the packages in `uv.lock` are audited once more, for a vulnerability that became known between the merge and the release. The inputs `workflow`, `branch` and `wait-minutes` change which CI workflow and branch count and how long the gate waits.

### Release tags

A release tag is `v` followed by the version exactly as the version file of the project writes it. Every action compares the two as text, so the rule holds for any language, and a tag in another spelling stops the release before anything is published.

A Python project writes its versions as PEP 440 does and tags `v1.2.3`, `v1.0.0rc1` or `v1.2.3.post1`, never `v1.0.0-rc.1`. A project in another language tags in its own format, for example `v1.0.0-rc.1` for semver. Only `publish/ghcr` reads the version itself, to derive the image tags. Its input `version-scheme` is `pep440` by default and `semver` for other projects. A pre-release gets its exact version as image tag, no `1.2` and no `latest`.

### Trial runs

A manual run of `publish.yml` tries the image half: `publish/ghcr` builds and pushes `edge`, from the default branch only, since `edge` is public. `publish/pypi` with `dry-run: true` builds and checks everything but the version and asks PyPI whether it would take the files, without uploading and without credentials. If the version is on PyPI already, it warns without failing, since a trial usually runs before the version is raised.

The PyPI trial runs in a job of its own, `pypi-trial` in the example, without the environment and without `id-token: write`. Run in the upload job instead, every manual run would show up as a deployment of the PyPI environment and get an OIDC token it does not need. The upload job keeps `if: github.event_name == 'release'`, so it never runs by hand.

### One-time setup

- PyPI: a pending publisher per project, with the owner, the repository, the workflow file name `publish.yml` and the environment named in the job. PyPI takes a pending publisher for one project only, hence one environment per package.
- GitHub: that environment under Settings, Environments.
- ghcr.io: a new package is private even in a public repository. After the first push, switch it to public under the organisation's Packages.
- MCP Registry: nothing. The registry grants `io.github.benethos-hub/*` to the OIDC token of the workflow.

## Brand assets

Every repository of the organisation carries these files:

| File | Content |
| --- | --- |
| `assets/brand/icon.svg` | The icon. This is the source of the other two. |
| `assets/brand/icon.png` | The icon as PNG, 512 × 512 pixels |
| `assets/brand/social-preview.png` | The social preview image for GitHub, 1280 × 640 pixels |

Both PNG files are exported from the SVG. Whenever the SVG changes, export them again and commit them with the SVG or afterwards. The social preview also has to be uploaded in the repository settings under Social preview, because GitHub does not read it from the repository.

The rules are written once, in [actions/brand/assets](actions/brand/assets/action.yml), and applied twice.

### The check in the CI

`brand.yml` fails when a file is missing, is not an SVG or a PNG, does not have its size, or is older than the last change to `icon.svg`, which means its last commit comes before the last commit of the SVG. The check shows up in pull requests as `brand / Brand assets`. Add all three files before adding the job, otherwise the CI of the repository fails right away.

A failed check alone does not block a merge. To make it required, create a branch ruleset in the repository:

1. Open Settings, then Rules, then Rulesets, and choose New branch ruleset.
2. Set the enforcement status to Active and target the default branch.
3. Enable Require status checks to pass and add `brand / Brand assets` and the other checks of the CI.
4. Enable Restrict deletions and Block force pushes as well.

A check has to run once in the repository before it can be selected. With this ruleset, direct pushes to the default branch are rejected. Add the Repository admin role to the bypass list if you still want to push directly.

### The weekly report

`brand-report.yml` runs every Monday at 06:00 UTC and can be started by hand. It applies the same rules to all public repositories of the organisation, except archived ones, forks and this one, so it also covers repositories that have not added the check yet. It also compares the social preview uploaded in the repository settings with `social-preview.png`. The CI check leaves that out on purpose: the upload is a manual step in the settings and cannot be part of a pull request.

Problems are listed in the issue [Brand assets need fixing](https://github.com/benethos-hub/.github/issues?q=is%3Aissue+%22Brand+assets+need+fixing%22) in this repository. The report updates the issue on every run and closes it once all repositories meet the rules.

## Maintaining this repository

### How a change reaches the projects

The repositories call every workflow and action here at `main`. A change merged here reaches all of them on their next run, without a pull request in any of them.

Some actions call others here at `main` as well: the three publishing actions call `release/tag-matches-version`, `python-release-ci-passed.yml` calls `release/ci-passed` and `python-dependency-audit.yml`, the audits call `python/pip-audit`, `python-tests.yml` calls `coverage-badge`, and `brand.yml` calls `brand/assets`. GitHub resolves such a call to `main` even in a pull request here, so a pull request cannot try a changed chain. The tests in `tests/` run the scripts and check the wiring, but the actions first run together after the merge. Only the workflows that `ci.yml` calls by local path are tried in a pull request, and the actions they call still come from `main`.

Two rules follow from that:

1. A change to an action and to the action that calls it lands in one commit, so `main` never holds one without the other.
2. After a change to a publishing action, try it in a project before its next release, through a manual run of its `publish.yml`.

### Checks of this repository

`ci.yml` checks this repository with its own `python-lint.yml`, `python-tests.yml`, `python-dependency-audit.yml` and `coverage-badge.yml`, called by local path, the way a project calls them. A job of its own checks the lockfiles of the actions. Ruff, pytest, pytest-cov, PyYAML and Mypy come from `uv.lock`, and their settings from `pyproject.toml`. The coverage covers the scripts the actions and workflows run.

A branch ruleset for `main` of this repository requires these checks:

- `lint / lint`
- `test / Python 3.11`, `test / Python 3.12`, `test / Python 3.13`, `test / Python 3.14` and `test / Python 3.15`
- `audit / Dependency audit`
- `Lockfiles of the actions`

The names come from the calling job and the job name in the called workflow. A change to either, or to the Python versions of `python-tests.yml`, changes the names, and the ruleset has to follow in the same step. Otherwise it waits for a check that never comes. `coverage-badge / Coverage badge` runs on a push only and is not required.

The scripts of the actions run with `uv run --no-project --python ">=3.11"`, so they get the lowest Python this repository is checked against, whichever Python the runner brings. Every action that needs uv installs it itself, so a caller never has to. A second install in the same job comes from the runner's tool cache. The uv cache in the GitHub Actions cache belongs to the job: no action saves it, and every workflow that does saves it under a key of its own, through `cache-suffix` or the Python version. `python-lowest-versions.yml` names its key after the Python version, `editable` and `requirements` of the call, so the calls of a repository with several packages do not share one. Jobs that run side by side would otherwise race for one key, and the loser would restore a cache another job filled. A test in `tests/` fails for a script call without that version, for an action that saves the uv cache, for two workflows with the same cache key, for an action that uses another action without its folder in `dependabot.yml`, and for a lockfile without its folder there.

### Dependencies

Every action in a workflow or action here is pinned to a commit, with its version in a comment beside it. Dependabot raises commit and comment together. Every Python tool has its version in a `uv.lock` and every Node tool in a `package-lock.json`, never in a workflow. The pip-audit that `python/pip-audit` runs is locked next to the action, so the lockfile decides in every repository that uses it, and so is the packer of `publish/mcpb`. Dependabot keeps every lockfile current.

A tool downloaded directly, pinned by version and checksum like the `mcp-publisher` of `publish/mcp-registry`, is invisible to Dependabot. It gets an entry in [.github/download-pins.yml](.github/download-pins.yml) instead. `download-pins-report.yml` checks every entry each Monday against the releases of its upstream and lists a newer release, with the version and checksum to paste, in the issue [Pinned downloads need an update](https://github.com/benethos-hub/.github/issues?q=is%3Aissue+%22Pinned+downloads+need+an+update%22).

Both weekly reports keep their issue through [.github/actions/report-issue](.github/actions/report-issue/action.yml): one open issue per report, updated on every run and closed once nothing is left to report.

## Organisation files

GitHub applies these files to every repository of the organisation that has no file of its own. They are not part of the repositories themselves, so they are missing from clones and downloads.

| File | Purpose |
| --- | --- |
| [FUNDING.yml](FUNDING.yml) | Sponsor links shown on every repository |
| [SECURITY.md](SECURITY.md) | The security policy. A repository only needs its own if it has something specific to say, for example what counts as a vulnerability in that project. |
| [profile/README.md](profile/README.md) | The organisation profile shown on github.com/benethos-hub |

The security policy asks for private reports under Security, Report a vulnerability. That button only appears when private vulnerability reporting is enabled in the security settings of the repository. Enable it in every public repository.
