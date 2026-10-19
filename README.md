# .github

Organisation defaults for benethos-hub. The organisation profile lives in [profile/README.md](profile/README.md).

## Contents

### Organisation files

| Path | Purpose |
| --- | --- |
| [FUNDING.yml](FUNDING.yml) | Sponsor links for every repository without its own funding file |
| [SECURITY.md](SECURITY.md) | Security policy for every repository without its own policy |
| [profile/](profile/) | Organisation profile shown on github.com/benethos-hub |
| [.github/dependabot.yml](.github/dependabot.yml) | Weekly updates for the actions pinned in the workflows and actions of this repository |
| [.github/download-pins.yml](.github/download-pins.yml) | Downloads pinned by version and checksum, which Dependabot cannot see. One entry per download. |
| [.github/scripts/](.github/scripts/) | Scripts the workflows of this repository run themselves |
| [.github/actions/](.github/actions/) | Actions the workflows of this repository use themselves, such as `report-issue`, which keeps the one issue of each weekly report |
| [tests/](tests/) | Tests for the scripts of the actions and for how the workflows wire them |
| [pyproject.toml](pyproject.toml), [uv.lock](uv.lock) | The tools for the checks of this repository (Ruff, pytest, pytest-cov, PyYAML, Mypy), locked, with their settings |

### Workflows

Workflows have to live directly in `.github/workflows`, because GitHub ignores subfolders there. Workflows for Python projects therefore start with `python-`. Each reusable workflow names the call for a repository's CI in its header comment.

| Workflow | Kind | Purpose |
| --- | --- | --- |
| [brand.yml](.github/workflows/brand.yml) | reusable | Check of the brand assets of a repository |
| [brand-report.yml](.github/workflows/brand-report.yml) | scheduled | Weekly report on the brand assets of all repositories |
| [download-pins-report.yml](.github/workflows/download-pins-report.yml) | scheduled | Weekly report on pinned downloads with a newer release or a checksum that is not the official one |
| [python-lint.yml](.github/workflows/python-lint.yml) | reusable | Lockfile in step with `pyproject.toml`, Ruff and Mypy |
| [python-tests.yml](.github/workflows/python-tests.yml) | reusable | Tests on every supported Python version, with coverage on the newest |
| [python-lowest-versions.yml](.github/workflows/python-lowest-versions.yml) | reusable | Tests against the lowest dependency versions that `pyproject.toml` allows |
| [python-dependency-audit.yml](.github/workflows/python-dependency-audit.yml) | reusable | Known vulnerabilities in the packages pinned in `uv.lock` |
| [python-release-ci-passed.yml](.github/workflows/python-release-ci-passed.yml) | reusable | Release gate: nothing is published before the CI run of the release commit on the default branch has passed |
| [ci.yml](.github/workflows/ci.yml) | push and pull request | Checks this repository with its own `python-lint.yml`, `python-tests.yml` and `python-dependency-audit.yml`, called by local path, so a pull request tries a change to them before it reaches the projects |

### Actions

Actions may live in subfolders. Those for Python projects are in `actions/python/`, those that guard a release in `actions/release/`, those that publish somewhere in `actions/publish/`, and the brand rules in `actions/brand/`. Every action that needs uv installs it itself, so a caller never has to. A second install in the same job comes from the cache. The scripts of the actions run with `uv run --no-project --python ">=3.11"`, so they get the lowest Python this repository is checked against, whichever Python the runner brings. A test in `tests/` fails for a call without it.

| Action | Purpose |
| --- | --- |
| [brand/assets](actions/brand/assets/action.yml) | Checks the brand assets of the checked-out repository. The rules are written once, in `brand_assets.py` next to it, which the CI check `brand.yml` and the weekly brand report both apply. |
| [python/pip-audit](actions/python/pip-audit/action.yml) | Checks pinned Python packages for known vulnerabilities. Used by `python-dependency-audit.yml` and `python-lowest-versions.yml`, so both apply the same rules and waivers. |
| [publish/pypi](actions/publish/pypi/action.yml) | Builds a Python package with uv, checks that the wheel carries the version of the release tag and every file the repository names, and uploads it through Trusted Publishing. A composite action, because Trusted Publishing identifies the workflow of the uploading job, so that job stays in the repository. In a uv workspace, `package` names the member. `dry-run: true` builds and checks everything but the version and asks PyPI about the files without uploading, for a trial before the first release. It does not tell whether the version is on PyPI already. |
| [publish/ghcr](actions/publish/ghcr/action.yml) | Builds a multi-arch container image and pushes it to ghcr.io, tagged from the release (`1.2.3`, `1.2`, `latest` for a full release, `edge` for a manual run). Then reads the published index back: every tag must be the same index, with the description, source, version and every platform built. One image per call, so a repository with several images calls it from a matrix. |
| [publish/mcpb](actions/publish/mcpb/action.yml) | Takes over once the repository has staged its Claude Desktop bundle: checks its version against the release tag, validates and packs it, holds the packed file to the staged tree byte for byte, and attaches it to the release with and without its version. The packer and everything beneath it are locked in a `package-lock.json` next to the action. |
| [publish/mcp-registry](actions/publish/mcp-registry/action.yml) | Publishes a `server.json` to the MCP Registry. Checks its version against the release tag, fills in the checksum of the release's Claude Desktop bundle, logs in with the workflow's OIDC token and retries a refusal, with a fallback without the bundle. The version of `mcp-publisher` is pinned here for all repositories. |
| [release/tag-matches-version](actions/release/tag-matches-version/action.yml) | Fails unless the release tag is the version in a `pyproject.toml` or in a JSON file such as `manifest.json` or `server.json`. Meant as the first step of every job that publishes. |
| [release/ci-passed](actions/release/ci-passed/action.yml) | Waits for the CI run of the pushed commit on the default branch and fails unless it succeeded. The logic is in `ci_passed.py` next to it. Used by `python-release-ci-passed.yml`. |

Every Python tool has its version in a `uv.lock` and every Node tool in a `package-lock.json`, never in a workflow. The pip-audit that `python/pip-audit` runs is locked in a `uv.lock` next to the action, so the lockfile decides in every repository that uses it. Dependabot keeps both lockfiles current.

An action that uses another action itself needs its folder in `.github/dependabot.yml`, and so does every folder with a `uv.lock`. A test in `tests/` fails otherwise.

A tool downloaded directly, pinned by version and checksum like the `mcp-publisher` of `publish/mcp-registry`, is invisible to Dependabot. It gets an entry in [.github/download-pins.yml](.github/download-pins.yml) instead. The Download pins report checks every entry each week against the releases of its upstream and lists a newer release, with the version and checksum to paste, in the issue [Pinned downloads need an update](https://github.com/benethos-hub/.github/issues?q=is%3Aissue+%22Pinned+downloads+need+an+update%22).

## Release gate

A version on PyPI cannot be replaced. `python-release-ci-passed.yml` therefore lets a release through only when the push of the release commit to the default branch ran `ci.yml` and that run succeeded. It waits up to 30 minutes for a run still in progress. A commit that never reached the default branch has no such run, and the gate stops the release after five minutes.

Call it first in the publish workflow of a repository and let every upload need it:

```yaml
jobs:
  ci-passed:
    uses: benethos-hub/.github/.github/workflows/python-release-ci-passed.yml@main
    permissions:
      actions: read
      contents: read
    with:
      audit: true

  pypi-publish:
    needs: ci-passed
```

The calling job has to grant `actions: read`, because a reusable workflow never gets more rights than its caller. With `audit: true`, the packages in `uv.lock` are checked for known vulnerabilities as well. That catches a vulnerability that became known between the merge and the release. The inputs `workflow`, `branch` and `wait-minutes` change which CI workflow and branch count and how long the gate waits.

## Changing shared workflows and actions

The repositories call every workflow and action here at `@main`. A change merged here reaches all of them on their next run, without a pull request in any of them.

Some actions call others here at `@main` as well: `publish/ghcr`, `publish/mcpb` and `publish/mcp-registry` call `release/tag-matches-version`, `python-release-ci-passed.yml` calls `release/ci-passed` and `python-dependency-audit.yml`, and `python-dependency-audit.yml` and `python-lowest-versions.yml` call `python/pip-audit`. GitHub resolves such a call to `main` even in a pull request here. So a pull request cannot try a changed chain. Its tests in `tests/` run the scripts and check the wiring, but the actions themselves first run together after the merge. Only `python-lint.yml`, `python-tests.yml` and `python-dependency-audit.yml` are tried in a pull request, because `ci.yml` calls them by local path. The actions they call still come from `main`.

Two rules follow from that:

1. A change to an action and to the action that calls it lands in one commit, so `main` never holds one without the other.
2. After a change to a publishing action, try it in a project before its next release, through a manual run: `publish/ghcr` pushes `edge`, and `publish/pypi` has `dry-run: true`.

## Release tags

A release tag is `v` followed by the version exactly as the project's version file writes it. Every action compares the two as text, so the rule holds for any language, and a tag in another spelling stops the release before anything is published.

A Python project writes its versions as PEP 440 does and tags `v1.2.3`, `v1.0.0rc1` or `v1.2.3.post1`, never `v1.0.0-rc.1`. A project in another language tags in its own format, for example `v1.0.0-rc.1` for semver.

Only `publish/ghcr` reads the version itself, to derive the image tags. Its input `version-scheme` is `pep440` by default and `semver` for other projects. A pre-release gets its exact version as image tag, no `1.2` and no `latest`.

## Security policy

GitHub shows [SECURITY.md](SECURITY.md) on every repository of the organisation that has no `SECURITY.md` of its own. A repository only needs its own file if it has something specific to say, for example what counts as a vulnerability in that project. The file is not part of the repositories themselves, so it is missing from clones and downloads.

The policy asks for private reports under Security → Report a vulnerability. That button only appears when private vulnerability reporting is enabled in the security settings of the repository. Enable it in every public repository.

## Brand assets

Every repository of the organisation carries these brand assets:

| File | Content |
| --- | --- |
| `assets/brand/icon.svg` | The icon. This is the source for the other files. |
| `assets/brand/icon.png` | The icon as PNG, 512 × 512 pixels |
| `assets/brand/social-preview.png` | The social preview image for GitHub, 1280 × 640 pixels |

Both PNG files are exported from the SVG. Whenever the SVG changes, export them again and commit them together with the SVG or afterwards. The social preview also has to be uploaded in the repository settings under Social preview, because GitHub does not read it from the repository.

Two workflows enforce these rules.

### Check in the repository CI

`brand.yml` is a reusable workflow. It fails in these cases:

- one of the three files is missing
- `icon.svg` is not an SVG or one of the PNG files is not a PNG
- a PNG file does not have its required size
- a PNG file is out of date, which means the last commit that changed it is older than the last commit that changed `icon.svg`

To use it, add this job to the CI workflow of the repository:

```yaml
jobs:
  brand:
    uses: benethos-hub/.github/.github/workflows/brand.yml@main
```

The check shows up in pull requests as `brand / Brand assets`. Add all three files before adding the job, otherwise the CI of the repository fails right away.

### Blocking merges

A failed check alone does not block a merge. To make it required, create a branch ruleset in the repository:

1. Open Settings, then Rules, then Rulesets, and choose New branch ruleset.
2. Set the enforcement status to Active and target the default branch.
3. Enable Require status checks to pass and add `brand / Brand assets`.
4. Enable Restrict deletions and Block force pushes as well.

The check has to run once in the repository before it can be selected. With this ruleset, direct pushes to the default branch are rejected. Add the Repository admin role to the bypass list if you still want to push directly.

### Organisation report

`brand-report.yml` runs every Monday at 06:00 UTC and can be started by hand in the Actions tab. It applies the same rules to all public repositories of the organisation, except archived ones, forks and this repository. It does not depend on the check above, so it also covers repositories that have not added it yet.

The report also compares the social preview uploaded in the repository settings with `assets/brand/social-preview.png`. Both have to be the same file. The CI check leaves this out on purpose: the upload is a manual step in the settings and cannot be part of a pull request, so the check would fail on every pull request that changes the image.

Problems are listed in the issue [Brand assets need fixing](https://github.com/benethos-hub/.github/issues?q=is%3Aissue+%22Brand+assets+need+fixing%22) in this repository. The workflow updates the issue on every run and closes it once all repositories meet the rules.
