# Freshness: a package-lock.json

Part of [FRESHNESS.md](../FRESHNESS.md).

## A package-lock.json

A repository can keep a `package-lock.json` the workflow does not read, such as a small one beside a vendored JavaScript file that records its version. Two actions measure it. `freshness.yml` has no `ecosystem: npm`, so each action is called as a job of the repository, one job per action, because each job leaves one artifact `freshness-<job>`.

```yaml
jobs:
  npm-outdated:
    name: Outdated npm packages
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha> # vX
        with:
          persist-credentials: false
      - uses: benethos-hub/.github/actions/node/freshness-outdated@main
        with:
          findings: ${{ runner.temp }}/freshness/npm-outdated
          directory: assets/vendor
      - uses: actions/upload-artifact@<sha> # vX
        with:
          name: freshness-npm-outdated
          path: ${{ runner.temp }}/freshness/npm-outdated

  npm-audit:
    name: Known npm vulnerabilities
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha> # vX
        with:
          persist-credentials: false
      - uses: benethos-hub/.github/actions/node/freshness-audit@main
        with:
          findings: ${{ runner.temp }}/freshness/npm-audit
          directory: assets/vendor
      - uses: actions/upload-artifact@<sha> # vX
        with:
          name: freshness-npm-audit
          path: ${{ runner.temp }}/freshness/npm-audit

  freshness:
    needs: [npm-outdated, npm-audit]
    if: ${{ !cancelled() }}
    uses: benethos-hub/.github/.github/workflows/freshness.yml@main
    permissions:
      contents: read
      issues: write
    with:
      issue-title: Pinned versions have newer releases
      extra-jobs: npm-outdated npm-audit
```

| Input | What it does |
| --- | --- |
| `findings` | The folder for `status.json` and `findings.jsonl`. The upload step takes it from there. |
| `directory` | The folder with the `package-lock.json`, relative to the repository. Default the root. The report shows it in `where`, as `assets/vendor/package-lock.json`. |
| `ignore-vulns` | `freshness-audit` only. Vulnerability IDs to waive, separated by spaces. The input of the same name of `freshness.yml` does not reach this job. |

**Newest means the highest stable version, not the dist-tag `latest`.** `latest` can be older than the pin. With `htmx.org` locked at 4.0.0 and `latest` at 2.0.11, `npm outdated` never names 4.0.1, so `freshness-outdated` does not use it. It reads the list of versions from the registry and takes the highest one that has no pre-release part and is not deprecated, compared by semver. A finding is written only when that version is higher than the locked one, so a new 2.0.12 is no finding while 4.0.1 is locked. A deprecated version never counts as newest, even when `latest` points at it. No resolver is involved, so a finding has no `within_bounds` and the report leaves that column empty.

`direct` comes from the root entry of the lockfile, so what only a workspace member names counts as transitive. An entry marked `dev` has the scope `dev`, every other the scope `runtime`. Entries that do not come from `registry.npmjs.org`, such as a link, a git or file source or a package bundled inside its parent, are no finding, and the summary counts them. A package the registry does not know, unpublished or private, is a warning in the log and counted in the summary, not a finding.

`freshness-audit` runs `npm audit --json --package-lock-only --include=dev` in the folder, with the npm of the runner. It reads the lockfile alone and installs nothing. Each advisory is one finding, named by its GHSA ID. `fix` is set only when the audit names a version of that same package, and left out when only a parent can move. With two affected versions of one package, each advisory is named for both, because the audit does not say which advisory hit which.

Neither action runs code from a package. A registry or an audit endpoint that cannot be reached, a rate limit or a 5xx is `inconclusive` and leaves no `findings.jsonl`, so the run cannot close the issue. A vulnerability is a finding, not a failure. A missing lockfile or one without a `packages` key, which is lockfile version 1, fails the action.
