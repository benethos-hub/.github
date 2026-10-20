# Setting up a new repository

These steps give a new repository of the organisation everything the existing ones have. They follow the order in which each step needs the one before it. The example is a Python project managed with uv. A project that publishes nothing stops after step 5.

1. **Brand assets.** Add `assets/brand/icon.svg`, `icon.png` and `social-preview.png`, and upload the social preview in the settings. See [Brand assets](brand-assets.md).
2. **CI.** Add `.github/workflows/ci.yml` with the jobs of the example in [CI of a Python project](ci.md). The brand assets have to be there first, otherwise `brand / Brand assets` fails right away.
3. **Dependabot.** Add `.github/dependabot.yml` with an entry for `uv`, `github-actions` and every Dockerfile folder. See [Repository settings](repository-settings.md#dependabot).
4. **Badges.** Open the README with the badge rows from [Badges](badges.md). The coverage badge shows up after the first push to `main`.
5. **Settings.** Once the CI has run on `main`, set the general settings, the branch protection with the check names of the CI, the security settings and the Actions permissions. See [Repository settings](repository-settings.md). From then on, every change reaches `main` through a pull request.
6. **Publishing.** Add `.github/workflows/publish.yml` from the example in [Publishing a release](releases.md), with the jobs the project needs. Then do the one-time setup there: the pending publisher on PyPI and one environment per package, open to tags `v*` only.
7. **Release tags.** Add the tag ruleset `Release tags`. See [Repository settings](repository-settings.md#release-tags).
8. **First trial.** Start `publish.yml` by hand on `main`. The gate checks the CI run, `pypi-trial` builds and checks the packages without uploading, and `ghcr-publish` pushes `edge`. Switch a new container package to public afterwards.
9. **First release.** Raise the version, merge, and publish a release with the tag `v` and that version. See [Release tags](releases.md#release-tags).

The workflows and actions themselves need no copy. The repository calls them here at `main`, and a change here reaches it on its next run.
