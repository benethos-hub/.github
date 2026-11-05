# CodeQL

[actions/codeql](../actions/codeql/action.yml) runs CodeQL on a checkout in one step, with the security and the quality queries, and uploads the findings to code scanning. [codeql.yml](../.github/workflows/codeql.yml) is the job around it. GitHub's default setup of code scanning runs the security queries alone, and the quality queries are otherwise part of a paid product. This is the free way to both: the Actions minutes of a public repository cost nothing.

The findings appear under Security, Code scanning, next to those of the default setup before it. The security queries find what reaches an attacker, such as an injection or a path built from input. The quality queries find what makes code hard to keep, such as an unreachable branch, a comparison that is always true, an unused import or a function with too many return types. They overlap in part with Ruff and Mypy, which the lint workflow runs already, and add the rules about reliability that a linter does not know. A finding is a warning or a note, not an error, and never fails the job.

## Calling it

Two calls, one for changes and one for new queries:

```yaml
# In ci.yml, beside the other jobs. Every push and pull request on main.
  codeql:
    uses: benethos-hub/.github/.github/workflows/codeql.yml@main
    permissions:
      contents: read
      security-events: write
    with:
      languages: python,actions
```

```yaml
# codeql.yml of the repository. GitHub adds queries over time, and only a run
# on a schedule reads code nobody changed.
name: CodeQL

on:
  schedule:
    - cron: "30 5 * * 1"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  codeql:
    uses: benethos-hub/.github/.github/workflows/codeql.yml@main
    permissions:
      contents: read
      security-events: write
    with:
      languages: python,actions
```

Both file under the same category, so each run refreshes the analysis the last one left and nothing is counted twice. A repository with JavaScript or TypeScript names `python,javascript-typescript,actions`. The calling job grants `security-events: write`, a reusable workflow never gets more than its caller. The check is named `codeql / CodeQL` and is not a required check.

| Input | What it does |
| --- | --- |
| `languages` | The languages to analyse, comma separated, as CodeQL names them: `python`, `javascript-typescript`, `actions`. Default `python,actions`. |
| `queries` | The query suites or queries, comma separated. Default `security-and-quality`. `security-extended` adds more security queries, empty runs the default suite of the security queries alone. |
| `packs` | CodeQL packs to run as well, comma separated, as `scope/name` or `scope/name@version`. |
| `config-file` | The path of a CodeQL configuration file in the repository, for paths to leave out and queries to filter. The one place for a rule a repository does not want, as `query-filters` with the reason beside it. |
| `config` | The same configuration as YAML in the call, for a repository without a file of its own. Takes precedence over `config-file`. |
| `build-mode` | `none` or `autobuild`. Empty lets CodeQL choose, which is `none` for the languages here. `manual` is not possible, a build between the two halves of the analysis needs the two actions of github/codeql-action in a job of the repository itself. |
| `category` | The name code scanning files the analysis under. Default `codeql`. Two analyses of one commit need two names. |
| `trusted-owners` | Owners whose actions and workflows may be called at a tag or a branch without an alert from the query `actions/unpinned-tag`, separated by spaces. Empty takes the owner of the repository, so the calls of the organisation's own actions and workflows at `main` pass. `none` writes no model and reports them. An owner with a leading `!` is distrusted, also `actions`, `github` and `advanced-security`, which CodeQL trusts by default. |
| `upload` | `always`, `failure-only` or `never`. Default `always`. A pull request from a fork gets `never` whatever is set, since its token may not upload, and the analysis still runs. |
| `upload-database` | Upload the CodeQL database as well, for debugging queries against it. Default off, it costs time on every run. |
| `tools` | A fixed CodeQL bundle, as a URL or a version, instead of the one the action brings. |
| `ram`, `threads` | The memory in MB and the threads CodeQL may use. Empty takes what the runner has. |
| `debug` | Debug mode of CodeQL, with its artifacts. Default off. |
| `runs-on` | The runner of the job, `ubuntu-latest` by default. Workflow only. |
| `timeout-minutes` | Time limit for the job, 30 by default. Workflow only. |
| `token` | The token for the upload. Action only, the workflow uses the token of its job. |

Every input but `trusted-owners` and the last three goes through to [github/codeql-action](https://github.com/github/codeql-action) unchanged, its documentation has the detail.

The organisation's actions and workflows are called at `main`, see [Maintaining this repository](maintaining.md), and the query `actions/unpinned-tag` reports every such call unless it trusts the owner. The action therefore writes a CodeQL model pack with the trusted owners into `.github/codeql/extensions/trusted-owners/` of the checkout before the analysis, two files that CodeQL finds there by itself. Nothing is committed, a repository needs no file of its own, and the call stays as above. The pack is written only when `actions` is among the languages. The action leaves two outputs, `sarif` with the folder of the SARIF files and `sarif-id` of the upload, for a job that keeps the results as an artifact as well.

## Leaving the default setup

Code scanning has two setups and a repository runs one of them. The default setup is a setting and needs no file. The advanced setup is a workflow, this one. While the default setup is on for a language, GitHub rejects every upload for that language from a workflow, and the analyse step fails with a message that names the default setup. The order is therefore:

1. Merge the job into `ci.yml` and the workflow on the schedule. Their first runs fail at the upload, which is expected.
2. Switch the repository to the advanced setup: Settings, Code security, Code scanning, the menu of CodeQL analysis, Switch to advanced. Or through the API:

   ```sh
   gh api -X PATCH repos/benethos-hub/<repo>/code-scanning/default-setup -f state=not-configured
   ```

3. Run `codeql.yml` by hand once, or push. From then on the workflow is the analysis, and the alerts of the default setup close as fixed where the new analysis does not find them.

The way back is the same setting. Switching the default setup on again stops the uploads of the workflow until it is removed.

## The first findings

The quality queries find something in most repositories on their first run. Each alert names the rule and the place. An alert that is right is fixed. One that does not apply is dismissed in the Security tab with the reason, so that a new alert stands out. A rule that never applies to a repository goes into its CodeQL configuration file as a `query-filters` entry with the reason beside it, and `config-file` names the file.

Whether a finding fails the code scanning check of a pull request is a setting of the repository: Settings, Code security, Code scanning, Protection rules, the threshold for check failure. Its default lets only errors fail, and the quality queries report none. Neither that check nor `codeql / CodeQL` is a required check in the branch protection of any repository, a merge never waits for a finding.

## A job of the repository

A repository that needs more than one step around the analysis, such as a generated file before it, calls the action in a job of its own with the same inputs:

```yaml
  codeql:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@<sha> # vX
      - run: ./generate.sh
      - uses: benethos-hub/.github/actions/codeql@main
        with:
          languages: python,actions
```

A compiled language with a build of its own does not fit into the action, because the build has to run between `init` and `analyze`. Such a job uses the two actions of github/codeql-action directly.
