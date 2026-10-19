# .github

Organisation defaults for benethos-hub. The organisation profile lives in [profile/README.md](profile/README.md).

## Contents

### Organisation files

| Path | Purpose |
| --- | --- |
| [FUNDING.yml](FUNDING.yml) | Sponsor links for every repository without its own funding file |
| [SECURITY.md](SECURITY.md) | Security policy for every repository without its own policy |
| [profile/](profile/) | Organisation profile shown on github.com/benethos-hub |
| [.github/dependabot.yml](.github/dependabot.yml) | Weekly updates for the actions pinned in the workflows of this repository |

### Workflows

Workflows have to live directly in `.github/workflows`, because GitHub ignores subfolders there. Workflows for Python projects therefore start with `python-`. Each reusable workflow names the call for a repository's CI in its header comment.

| Workflow | Kind | Purpose |
| --- | --- | --- |
| [brand.yml](.github/workflows/brand.yml) | reusable | Check of the brand assets of a repository |
| [brand-report.yml](.github/workflows/brand-report.yml) | scheduled | Weekly report on the brand assets of all repositories |
| [python-lint.yml](.github/workflows/python-lint.yml) | reusable | Lockfile in step with `pyproject.toml`, Ruff and Mypy |
| [python-tests.yml](.github/workflows/python-tests.yml) | reusable | Tests on every supported Python version, with coverage on the newest |
| [python-lowest-versions.yml](.github/workflows/python-lowest-versions.yml) | reusable | Tests against the lowest dependency versions that `pyproject.toml` allows |
| [python-dependency-audit.yml](.github/workflows/python-dependency-audit.yml) | reusable | Known vulnerabilities in the packages pinned in `uv.lock` |

### Actions

Actions may live in subfolders. Those for Python projects are in `actions/python/`.

| Action | Purpose |
| --- | --- |
| [python/pip-audit](actions/python/pip-audit/action.yml) | Checks pinned Python packages for known vulnerabilities. Used by `python-dependency-audit.yml` and `python-lowest-versions.yml`, so both apply the same rules and waivers. |

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
