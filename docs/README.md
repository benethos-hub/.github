# Documents

The documents of the organisation repository. Each page covers one topic
of the shared process and how a repository adopts it. A page with more
than one part keeps the parts in a folder of its own, named like the
page.

**Contents**

- [A new repository](#a-new-repository)
- [CI and checks](#ci-and-checks)
- [Releases and reports](#releases-and-reports)
- [Conventions](#conventions)
- [This repository](#this-repository)

## A new repository

| Document | What it covers |
| --- | --- |
| [NEW-REPOSITORY.md](NEW-REPOSITORY.md) | The steps that give a new repository everything the existing ones have, in order. |
| [REPOSITORY-SETTINGS.md](REPOSITORY-SETTINGS.md) | The settings in GitHub: merging, branch protection, release tags, environments, security, Actions and Dependabot. |

## CI and checks

| Document | What it covers |
| --- | --- |
| [CI.md](CI.md) | The `ci.yml` of a project, the reusable workflows and the names of their checks. |
| [CODEQL.md](CODEQL.md) | The CodeQL analysis with the security and the quality queries, as a job of the CI and on a schedule, and the setting a repository changes for it. |
| [DOCKERFILE-CHECKS.md](DOCKERFILE-CHECKS.md) | hadolint, Trivy and Checkov over the Dockerfiles of a repository, each as a job of the CI with its findings in code scanning, and the shared SARIF report any scanner can use. |
| [BADGES.md](BADGES.md) | The badge rows of every README, their colours and logos, and the coverage badge. |
| [BRAND-ASSETS.md](BRAND-ASSETS.md) | The icon and social preview of every repository, the check in the CI and the weekly report. |

## Releases and reports

| Document | What it covers |
| --- | --- |
| [RELEASES.md](RELEASES.md) | The `publish.yml` of a project, the publishing actions, the release gate, release tags, trial runs and the one-time setup. |
| [REPORTS.md](REPORTS.md) | How a scheduled workflow of any repository keeps its result in one issue. |
| [FRESHNESS.md](FRESHNESS.md) | The daily report of what a repository pins and what is newer. The overview, and in [freshness/](freshness/) the call, a job of the repository, a `package-lock.json` and another language. |

## Conventions

| Document | What it covers |
| --- | --- |
| [MCP-SERVER-STATUS.md](MCP-SERVER-STATUS.md) | The status tool every MCP server of the organisation offers: its quick answer, the details part, secrets, tests and documentation. |

## This repository

| Document | What it covers |
| --- | --- |
| [MAINTAINING.md](MAINTAINING.md) | How a change here reaches the projects, the checks of this repository and its dependencies. |
