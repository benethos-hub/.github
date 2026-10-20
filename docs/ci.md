# CI of a Python project

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
| [brand.yml](../.github/workflows/brand.yml) | The brand assets, see [Brand assets](brand-assets.md) | none |
| [python-lint.yml](../.github/workflows/python-lint.yml) | `uv.lock` in step with `pyproject.toml`, Ruff lint and format, Mypy. The tools and their settings come from the project. | `sync-args`, `timeout-minutes` |
| [python-tests.yml](../.github/workflows/python-tests.yml) | pytest on every supported Python against `uv.lock`. The newest version also measures the coverage and enforces its floor, 80 % by default. | `python-versions`, `coverage-python`, `sync-args`, `cov`, `cov-fail-under`, `badge`, `timeout-minutes` |
| [python-lowest-versions.yml](../.github/workflows/python-lowest-versions.yml) | The tests against the lowest versions `pyproject.toml` allows, on the oldest supported Python, without the lockfile. With `audit: true`, those versions are audited too. | `python-version`, `editable`, `requirements`, `pytest-args`, `audit`, `ignore-vulns`, `timeout-minutes` |
| [python-dependency-audit.yml](../.github/workflows/python-dependency-audit.yml) | Every version pinned in `uv.lock`, for every platform and Python, against PyPI and OSV. A vulnerability without a fix is waived by ID. | `ignore-vulns` |
| [coverage-badge.yml](../.github/workflows/coverage-badge.yml) | Nothing. It publishes the coverage badge, of any language, see [Coverage badge](badges.md#coverage-badge). | `artifact`, `branch` |

## Check names

The checks are named after the calling job and the job inside the workflow: `lint / lint`, `test / Python 3.15`, `lowest-versions / Python 3.11`, `audit / Dependency audit` and `brand / Brand assets`. These are the names the branch protection requires, see [Repository settings](repository-settings.md#branch-protection). A project names its Python versions in `with:` even where they equal the defaults, so that a changed default here never moves its tests without a word.

Coverage is measured on one version only, because it slows the older ones down noticeably. A required check on `test / Python 3.15` is what makes the floor block a merge.

## Several packages

A repository with several packages, such as a uv workspace, calls `python-lowest-versions.yml` once per package, each with its own `editable` and `pytest-args` and a job name of its own, for example `lowest-mcp` or `lowest-client`. Each call caches under a key of its own, so the calls can run side by side.
