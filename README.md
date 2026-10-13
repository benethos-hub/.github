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

The SVG is the source. The PNG is exported from it and is 512 × 512 pixels. Whenever the SVG changes, export the PNG again and commit it together with the SVG or afterwards.

Two workflows enforce these rules.

### Check in the repository CI

`brand.yml` is a reusable workflow. It fails in these cases:

- one of the two files is missing
- `icon.svg` is not an SVG or `icon.png` is not a PNG
- `icon.png` is not 512 × 512 pixels
- `icon.png` is out of date, which means the last commit that changed it is older than the last commit that changed `icon.svg`

To use it, add this job to the CI workflow of the repository:

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

`brand-report.yml` runs every Monday at 06:00 UTC and can be started by hand in the Actions tab. It applies the same rules to all public repositories of the organisation, except archived ones, forks and this repository. It does not depend on the check above, so it also covers repositories that have not added it yet.

Problems are listed in the issue [Brand assets need fixing](https://github.com/benethos-hub/.github/issues?q=is%3Aissue+%22Brand+assets+need+fixing%22) in this repository. The workflow updates the issue on every run and closes it once all repositories meet the rules.
