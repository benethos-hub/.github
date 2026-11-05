# Dockerfile checks

Three scanners read the Dockerfiles of a repository and judge their form, each as an action and as a reusable workflow around it, and one shared action carries their findings to the step summary and to code scanning. A repository picks the scanner it wants, one or all three. They know no language of the project, only the files they read.

| Scanner | Action and workflow | What it reads | What it finds |
| --- | --- | --- | --- |
| hadolint | [dockerfile-lint](../actions/dockerfile-lint/action.yml), [dockerfile-lint.yml](../.github/workflows/dockerfile-lint.yml) | Every file the patterns match, `**/Dockerfile*` by default | The form of a Dockerfile: an image without a tag or with `latest`, a package without a version, `apt-get` without cleaning up, `ADD` where `COPY` would do, no `USER`, the shell form of `CMD`, and the shell lines of every `RUN` through ShellCheck |
| Trivy | [trivy-config](../actions/trivy-config/action.yml), [trivy-config.yml](../.github/workflows/trivy-config.yml) | A folder, with every Dockerfile, Kubernetes manifest, Helm chart, Terraform, CloudFormation, Azure ARM and Ansible file in it | Misconfigurations: a root user, a secret in `ENV` judged by the variable's name, an image without a tag, an open port, and the same for the other types |
| Checkov | [checkov](../actions/checkov/action.yml), [checkov.yml](../.github/workflows/checkov.yml) | A folder, the Dockerfiles by default, other frameworks on request | A user, a health check, `COPY` over `ADD`, an image with a tag, no secret in `ENV`, about 30 checks for Dockerfiles and many more for infrastructure as code |

None of the three reads a compose file. The images a compose file names are a matter of the [freshness report](freshness.md), which reads them for their tags and digests.

The scanners report, the repository decides. Each scanner leaves a SARIF file, and [sarif-report](../actions/sarif-report/action.yml) writes a table of it to the step summary, uploads it to code scanning under the scanner's category, and fails the step only when a finding reaches `failure-level`, whose default is `none`. Whether a finding turns the code scanning check of a pull request red is the protection rule of the repository, Settings, Code security, Code scanning, Protection rules, Check failure, one threshold for every tool, see [Repository settings](repository-settings.md#the-code-scanning-check). `failure-level` is for a repository that wants the scanner's own job red regardless of that rule. The code scanning check exists on a pull request with an upload only. A run on a push or a schedule, and a pull request from a fork, ends green whatever the findings, which stay in the step summary and, once uploaded, in the Security tab. None of the checks is a required check.

## Choosing

Measured on the Dockerfiles of the organisation's repositories, which pin every image by tag and digest and switch to an unprivileged user: hadolint reported two warnings about the shell form of `HEALTHCHECK` and one about a variable whose name ends in `TOKEN` and whose value is a switch, and a note per `USER` line that names the user instead of an id. Trivy reported nothing but the name matches on `ENV`, three of them, each as CRITICAL: a variable ending in `TOKEN` set to `1`, a variable ending in `KEY_FILE` holding the path of a Docker secret, and one ending in `KEY_PROVIDER` set to `file`. Checkov reported nothing.

So for a repository with Dockerfiles alone, hadolint is the one to start with. It is one binary, fast, and its findings are about the file. Trivy earns its place once a repository has Kubernetes or Terraform files, or wants its images scanned for vulnerabilities later, which is another command of the same tool. Checkov covers the widest ground in infrastructure as code and is the heaviest to install. Any of them can run beside the others, each under its own category.

## Calling

Each workflow is one job, called from `ci.yml` beside the other jobs:

```yaml
  dockerfile-lint:
    uses: benethos-hub/.github/.github/workflows/dockerfile-lint.yml@main
    permissions:
      contents: read
      security-events: write
    with:
      files: containers/**/Dockerfile
      trusted-registries: docker.io ghcr.io

  trivy-config:
    uses: benethos-hub/.github/.github/workflows/trivy-config.yml@main
    permissions:
      contents: read
      security-events: write
    with:
      path: containers

  checkov:
    uses: benethos-hub/.github/.github/workflows/checkov.yml@main
    permissions:
      contents: read
      security-events: write
    with:
      directory: containers
```

The calling job grants `security-events: write`, a reusable workflow never gets more than its caller. The checks are named `dockerfile-lint / Dockerfile lint`, `trivy-config / Trivy config` and `checkov / Checkov`. A run on a schedule, so that a check the scanner adds later reads code nobody changed, goes into the same workflow of the repository that runs [CodeQL](codeql.md) weekly. Each run files under the scanner's category, so each refreshes the analysis the last one left.

A pull request from a fork has no token that may upload. The upload is left out there, so there is no code scanning check for it, the summary still shows every finding, and `failure-level` alone decides.

## The inputs

Every scanner takes these, and the workflows take them too, with `runs-on` and `timeout-minutes` on top and without `token`:

| Input | What it does |
| --- | --- |
| `failure-level` | The level from which a finding fails the step, after the upload: `none`, `note`, `warning` or `error`. The default `none` fails nothing, the code scanning check of the repository decides. A repository that wants the job red on its own sets a level on purpose, the levels of each scanner are below. |
| `category` | The name code scanning files the analysis under. Default the scanner's name: `dockerfile-lint`, `trivy-config`, `checkov`. Two scanners in one repository keep two categories. |
| `upload` | Upload the findings to code scanning. Default on. Off leaves them in the summary and, with `artifact`, in an artifact. |
| `artifact` | The name of an artifact to keep the SARIF file in. Empty keeps none. |
| `retention-days` | How many days the artifact is kept. Default 7. |
| `token` | The token for the upload, action only. The default is the token of the workflow, which needs `security-events: write`. |
| `runs-on`, `timeout-minutes` | Workflow only. The runner, `ubuntu-latest` by default, and the time limit, 10 minutes, 15 for Checkov. |

The levels in code scanning are the scanner's own, translated to the three SARIF has:

| Scanner | error | warning | note | Default `failure-level` |
| --- | --- | --- | --- | --- |
| hadolint | its `error` rules | its `warning` rules | `info` and `style` | `none`. `warning` takes the rules worth acting on |
| Trivy | HIGH and CRITICAL | MEDIUM | LOW | `none` |
| Checkov | every failed check | | | `none`. Any other level fails on any finding |

### dockerfile-lint

| Input | What it does |
| --- | --- |
| `files` | Glob patterns of the files to lint, separated by spaces, relative to the checkout. Default `**/Dockerfile*`. Without a match the run leaves an empty result and fails nothing. |
| `ignore` | Rule codes not to report, such as `DL3025 DL3066`. Say why in the call. |
| `trusted-registries` | Registries `FROM` may pull from, such as `docker.io ghcr.io`. An image from elsewhere is a finding. Empty trusts every registry. |
| `config` | The path of a `.hadolint.yaml` in the repository. Its ignore list and trusted registries come on top of the inputs, and it is the place for a rule's level or a label schema. |

hadolint is downloaded pinned by version and checksum in the action, the one place for all repositories. Dependabot cannot see a download, so the [Download pins report](maintaining.md#dependencies) opens an issue once a newer release is out.

### trivy-config

| Input | What it does |
| --- | --- |
| `path` | The folder to scan, relative to the checkout. Default the whole checkout. |
| `scanners` | The misconfiguration scanners to run, such as `dockerfile kubernetes`. Empty runs every one Trivy has. |
| `severity` | The severities to report, from `UNKNOWN LOW MEDIUM HIGH CRITICAL`. Empty reports every one. |
| `skip-dirs`, `skip-files` | Folders and files, or glob patterns, to leave out. |
| `ignorefile` | The path of a `.trivyignore` with the check ids to leave out, one per line with the reason as a comment. Empty takes `.trivyignore` in the folder scanned, when there is one. The place for a check that matches a name alone, such as DS-0031 on a variable called `*_KEY_FILE`. |
| `config` | The path of a `trivy.yaml` with any option of Trivy. |
| `checks`, `namespaces` | Folders of custom Rego checks and their namespaces. |
| `offline` | Do not fetch the checks bundle, use the one in the cache. Default off, and the cache of a fresh runner is empty, so this is for a runner of the repository's own. |

Trivy is downloaded pinned by version and checksum like hadolint. Its checks come from Trivy's registry on every run, so a run can find something new in code nobody changed.

### checkov

| Input | What it does |
| --- | --- |
| `directory` | The folder to scan, relative to the checkout. Default the whole checkout. |
| `framework` | The frameworks to run, such as `dockerfile kubernetes terraform`. Default `dockerfile`. Empty runs every one Checkov has, which takes longer and reads more. |
| `check` | Only these check ids, such as `CKV_DOCKER_2 CKV_DOCKER_3`. Empty runs every check of the frameworks. |
| `skip-check` | Check ids not to run. Say why in the call. |
| `skip-path` | Path patterns to leave out. |
| `config-file` | The path of a `.checkov.yaml` in the repository, with any option of Checkov. |
| `external-checks` | A folder of custom checks in the repository. |

Checkov is a Python tool, locked in the `uv.lock` next to the action, and Dependabot keeps it current. It runs with `--skip-download`, so nothing reaches the vendor's platform, and without the platform every finding is an error.

## A scanner of the repository's own

Any scanner that writes SARIF can use the same tail. The job runs it, then calls `sarif-report`:

```yaml
      - run: ./scan.sh --format sarif > "$RUNNER_TEMP/scan.sarif"
      - uses: benethos-hub/.github/actions/sarif-report@main
        with:
          sarif: ${{ runner.temp }}/scan.sarif
          tool: My scanner
          category: my-scanner
          failure-level: error
```

| Input | What it does |
| --- | --- |
| `sarif` | The SARIF file the scanner left. Required. |
| `tool` | The name in the heading of the summary. Empty takes the name the file carries. |
| `category` | The name code scanning files the analysis under. Required. |
| `upload`, `artifact`, `retention-days`, `failure-level`, `token` | As above. |

The outputs are `findings`, `errors`, `warnings`, `notes` and `highest`, for a step after it. A result without a level takes the default of its rule, and `warning` without that, as SARIF says. An empty file is uploaded as well, it closes the alerts of the category as fixed.

## The first findings

Each finding in the Security tab names the rule, the file and the line. One that is right is fixed. One that does not apply is dismissed there with the reason, or left out for good in the scanner's own file, `.hadolint.yaml`, `.trivyignore` or `.checkov.yaml`, with the reason beside it, so that a new finding stands out. A rule that never applies in the organisation can go into the `ignore` or `skip-check` of the call, with the reason in a comment.
