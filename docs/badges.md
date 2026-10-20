# Badges

The README of every repository opens with its badges, right after the title, in three rows, or more for a repository with several packages. A blank line between the rows keeps them apart.

## The rows

The first row says whether the project is in order and what it runs on:

1. CI, the status badge of `ci.yml`
2. Coverage, from the `badges` branch, see [Coverage badge](#coverage-badge). Only where the tests measure it.
3. License, read by shields.io from the `LICENSE` file. Only where the repository has one.
4. The language versions the project supports, read from where the project declares them.

The second row says where to get it: one badge per package on its registry and one container badge per image. A repository that publishes nothing has no second row.

A repository with several packages, such as a uv workspace, gives each package a row of its own instead. The packages people run come first and the libraries they build on last, in mailbox for example service, mcp, client and common. Each row holds the badge of the package on its registry first and, where the package has an image, its container badge after it. A blank line separates these rows as well, since GitHub shows lines without one in a single row. The sponsor row follows after the last package.

The third row holds the sponsor links, GitHub Sponsors and PayPal. The badges are served from [profile/badges](../profile/badges/) in this repository, the same files the organisation profile shows, so every repository carries the same two and a change here reaches all of them.

## Colours and logos

None of the badges carries a value written by hand, and all of them use the default style of shields.io. The colours are the same in every repository, and each one means something. The CI badge is green or red, as GitHub draws it. The coverage badge follows the usual scale, green from 80, bright green from 90 and red below 50. The licence badge keeps the colour shields.io gives the licence, green for a permissive one such as MIT and orange for copyleft. A version badge keeps the colour shields.io gives the version, orange below 1.0 and blue from 1.0 on, so a package before its first stable release is visible as such. The badge of the supported language versions is blue, with `color=blue` where shields.io would choose otherwise. The container badge carries the Docker blue `2496ED`. The sponsor badges keep the colours of their files.

Every badge of the first two rows carries a white logo from [simple-icons](https://simpleicons.org/), through `logo=<name>&logoColor=white`: the licence the Open Source Initiative, the language versions the language, the package its registry, the container Docker, and the coverage GitHub Actions, where it is measured, for every language. The CI badge brings its GitHub mark itself, and the sponsor badges have theirs in their files.

## To copy

```markdown
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/<owner>/<repo>/badges/coverage.json&logo=githubactions&logoColor=white)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/<owner>/<repo>?logo=opensourceinitiative&logoColor=white)](https://github.com/<owner>/<repo>/blob/main/LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/<package>?logo=python&logoColor=white)](https://pypi.org/project/<package>/)

[![PyPI <package>](https://img.shields.io/pypi/v/<package>?label=PyPI%20<package>&logo=pypi&logoColor=white)](https://pypi.org/project/<package>/)
[![Container <image>](https://img.shields.io/badge/ghcr.io-<image>-2496ED?logo=docker&logoColor=white)](https://github.com/<owner>/<repo>/pkgs/container/<image>)

[![Sponsor](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/sponsor.svg)](https://github.com/sponsors/BeneODev)
[![PayPal](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/paypal.svg)](https://paypal.me/BeneODev)
```

In the container badge, a dash in the image name is written as `--`, since shields.io reads a single dash as the separator.

## Other languages

The example is a Python project. The rule is the same for every language, only the two badges that read a package differ:

| Language | Versions, first row | Package, second row |
| --- | --- | --- |
| Python | `pypi/pyversions/<package>?logo=python` | `pypi/v/<package>?label=PyPI%20<package>&logo=pypi` |
| Go | `github/go-mod/go-version/<owner>/<repo>?logo=go` | `github/v/release/<owner>/<repo>?label=Release&logo=github`, since a module is fetched from the repository |
| Node | `node/v/<package>?logo=nodedotjs&color=blue` | `npm/v/<package>?label=npm%20<package>&logo=npm` |

Each is a path under `https://img.shields.io/`, with `&logoColor=white` added. The version badges keep the colour of shields.io, the Node versions badge would be green without `color=blue`.

This repository has no licence file and publishes nothing. Its first row goes on with the two weekly reports instead, which are status badges as well, and its second row is missing.

## Coverage badge

With `badge: true`, `python-tests.yml` reads the measured percentage and hands it to the action `coverage-badge`, which writes the JSON of a [shields.io endpoint badge](https://shields.io/badges/endpoint-badge), uploaded as the artifact `coverage-badge`. `coverage-badge.yml` then commits that file as `coverage.json` on the `badges` branch of the repository, which it creates on the first run. The branch carries nothing else, and the job needs `contents: write` for the push. Call it on a push to the default branch only, so the badge shows the coverage of that branch, and never make it a required check, since a pull request does not run it.

Only the measuring step knows the language. The action takes a percentage, and the workflow takes a file, so a project in another language brings a test workflow of its own that reads its coverage and calls the same two. The percentage is rounded down, so a badge at the floor means the floor holds. After the first push to the default branch, the badge can show "resource not found" for a few minutes: the README is online before the job has created the branch, and GitHub and shields.io cache that first answer. It corrects itself.
