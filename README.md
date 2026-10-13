# .github

Organisation defaults for benethos-hub. The organisation profile lives in [profile/README.md](profile/README.md).

| Path | Purpose |
| --- | --- |
| [FUNDING.yml](FUNDING.yml) | Sponsor links for every repository without its own funding file |
| [profile/](profile/) | Organisation profile shown on github.com/benethos-hub |
| [.github/workflows/brand.yml](.github/workflows/brand.yml) | Reusable check for the brand assets of a repository |
| [.github/workflows/brand-report.yml](.github/workflows/brand-report.yml) | Weekly report on brand assets across all repositories |

## Brand assets

Every repository of the organisation carries its icon in two formats:

```text
assets/brand/icon.svg
assets/brand/icon.png
```

Two workflows enforce this rule.

### Check in the repository CI

`brand.yml` is a reusable workflow. It fails if one of the files is missing, if `icon.svg` is not an SVG or if `icon.png` is not a PNG. To use it, add this job to the CI workflow of the repository:

```yaml
jobs:
  brand:
    uses: benethos-hub/.github/.github/workflows/brand.yml@main
```

The check shows up in pull requests as `brand / Icon present`. Add both files before adding the job, otherwise the CI of the repository fails right away.

### Blocking merges

A failed check alone does not block a merge. To make it required, create a branch ruleset in the repository:

1. Open Settings, then Rules, then Rulesets, and choose New branch ruleset.
2. Set the enforcement status to Active and target the default branch.
3. Enable Require status checks to pass and add `brand / Icon present`.
4. Enable Restrict deletions and Block force pushes as well.

The check has to run once in the repository before it can be selected. With this ruleset, direct pushes to the default branch are rejected. Add the Repository admin role to the bypass list if you still want to push directly.

### Organisation report

`brand-report.yml` runs every Monday at 06:00 UTC and can be started by hand in the Actions tab. It checks all public repositories of the organisation, except archived ones, forks and this repository. It does not depend on the check above, so it also covers repositories that have not added it yet.

Missing files are listed in the issue [Missing brand assets](https://github.com/benethos-hub/.github/issues?q=is%3Aissue+%22Missing+brand+assets%22) in this repository. The workflow updates the issue on every run and closes it once nothing is missing.
