# Brand assets

Every repository of the organisation carries these files:

| File | Content |
| --- | --- |
| `assets/brand/icon.svg` | The icon. This is the source of the other two. |
| `assets/brand/icon.png` | The icon as PNG, 512 × 512 pixels |
| `assets/brand/social-preview.png` | The social preview image for GitHub, 1280 × 640 pixels |

Both PNG files are exported from the SVG. Whenever the SVG changes, export them again and commit them with the SVG or afterwards. The social preview also has to be uploaded in the repository settings under Social preview, because GitHub does not read it from the repository.

The rules are written once, in [actions/brand/assets](../actions/brand/assets/action.yml), and applied twice.

## The check in the CI

`brand.yml` fails when a file is missing, is not an SVG or a PNG, does not have its size, or is older than the last change to `icon.svg`, which means its last commit comes before the last commit of the SVG. The check shows up in pull requests as `brand / Brand assets`. Add all three files before adding the job, otherwise the CI of the repository fails right away.

A failed check alone does not block a merge. It blocks one once the branch protection requires it, see [Repository settings](repository-settings.md#branch-protection).

## The weekly report

`brand-report.yml` runs every Monday at 06:00 UTC and can be started by hand. It applies the same rules to all public repositories of the organisation, except archived ones, forks and this one, so it also covers repositories that have not added the check yet. It also compares the social preview uploaded in the repository settings with `social-preview.png`. The CI check leaves that out on purpose: the upload is a manual step in the settings and cannot be part of a pull request.

Problems are listed in the issue [Brand assets need fixing](https://github.com/benethos-hub/.github/issues?q=is%3Aissue+%22Brand+assets+need+fixing%22) in this repository. The report updates the issue on every run and closes it once all repositories meet the rules.
