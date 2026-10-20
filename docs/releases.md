# Publishing a release

A release is published from the `publish.yml` of a project on the event `release`. Every upload is done by an action here. They are composite actions and not reusable workflows on purpose: PyPI's Trusted Publishing and the MCP Registry identify the workflow of the job that uploads, so that job has to stay in the project.

```yaml
on:
  release:
    types: [published]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  ci-passed:
    if: github.event_name == 'release' || github.ref == 'refs/heads/main'
    uses: benethos-hub/.github/.github/workflows/python-release-ci-passed.yml@main
    permissions:
      actions: read
      contents: read
    with:
      audit: true

  pypi-publish:
    if: github.event_name == 'release'
    needs: ci-passed
    runs-on: ubuntu-latest
    environment:
      name: pypi-benethos-example
      url: https://pypi.org/p/benethos-example
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@<sha> # vX
      - uses: benethos-hub/.github/actions/publish/pypi@main
        with:
          wheel-contains: benethos_example/py.typed

  pypi-trial:
    if: github.event_name == 'workflow_dispatch'
    needs: ci-passed
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<sha> # vX
      - uses: benethos-hub/.github/actions/publish/pypi@main
        with:
          dry-run: true
          wheel-contains: benethos_example/py.typed

  ghcr-publish:
    if: github.event_name == 'release' || github.ref == 'refs/heads/main'
    needs: ci-passed
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@<sha> # vX
      - uses: benethos-hub/.github/actions/publish/ghcr@main
        with:
          image: benethos-example
          dockerfile: containers/images/example/Dockerfile

  mcpb-bundle:
    if: github.event_name == 'release'
    needs: ci-passed
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@<sha> # vX
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<sha> # vX
      - run: uv run --no-project .github/publish/mcpb/build.py "$RUNNER_TEMP/bundle"
      - uses: benethos-hub/.github/actions/publish/mcpb@main
        with:
          staged: ${{ runner.temp }}/bundle
          name: benethos-example

  mcp-registry:
    if: github.event_name == 'release' && !github.event.release.prerelease
    needs: [pypi-publish, ghcr-publish, mcpb-bundle]
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@<sha> # vX
      - uses: benethos-hub/.github/actions/publish/mcp-registry@main
```

| Action | What it does | Inputs |
| --- | --- | --- |
| [release/ci-passed](../actions/release/ci-passed/action.yml) | Waits for the CI run of the released commit on the default branch and fails unless it succeeded. Used through `python-release-ci-passed.yml`. | `workflow`, `branch`, `wait-minutes`, `token` |
| [release/tag-matches-version](../actions/release/tag-matches-version/action.yml) | Fails unless the release tag is the version in a `pyproject.toml` or a JSON file such as `manifest.json` or `server.json`. The publishing actions run it first. | `file`, `tag` |
| [publish/pypi](../actions/publish/pypi/action.yml) | Builds sdist and wheel with uv, checks that the wheel is the package asked for, carries the version of the tag and every path in `wheel-contains`, and uploads through Trusted Publishing. A file already on PyPI with the same content is skipped, so a failed upload can be run again. In a uv workspace, `package` names the member, one job per member. | `package`, `wheel-contains`, `tag`, `dry-run` |
| [publish/ghcr](../actions/publish/ghcr/action.yml) | Builds a multi-arch image and pushes it to ghcr.io as `1.2.3`, `1.2` and `latest`, or `edge` from a manual run. Then reads the published index back: every tag the same index, with description, source, version and every platform. One image per call, a repository with several images uses a matrix. Each image keeps its own build cache. `cache-scope` names the scope a CI build of the same image writes to, so the release reuses its layers. | `image`, `dockerfile`, `context`, `platforms`, `description`, `version-scheme`, `version-file`, `cache-scope`, `token` |
| [publish/mcpb](../actions/publish/mcpb/action.yml) | Takes a staged Claude Desktop bundle, checks its version, validates and packs it, holds the packed file to the staged tree byte for byte, and attaches it to the release as `<name>-1.2.3.mcpb` and `<name>.mcpb`. The packer is locked in `package-lock.json` next to the action. | `staged`, `name`, `tag`, `token` |
| [publish/mcp-registry](../actions/publish/mcp-registry/action.yml) | Publishes a `server.json` to the MCP Registry: checks its version, fills in the checksum of the bundle on the release, logs in with the workflow's OIDC token, retries a refusal and falls back to the entry without the bundle. `mcp-publisher` is pinned here for all repositories. | `entry`, `tag`, `attempts`, `wait-seconds`, `token` |

## The release gate

A version on PyPI cannot be replaced. `python-release-ci-passed.yml` therefore lets a release through only when the push of the release commit to the default branch ran `ci.yml` and that run succeeded. It waits up to 30 minutes for a run still in progress. A commit that never reached the default branch has no such run, and the gate stops the release after five minutes. The calling job grants `actions: read`, because a reusable workflow never gets more rights than its caller.

The calling job runs only for a release or on the default branch, through `if: github.event_name == 'release' || github.ref == 'refs/heads/main'`. A manual run on another branch then skips the gate and every job after it, instead of failing after five minutes although nothing broke. The condition stays in the calling job and not in the reusable workflow, because GitHub does not rate a calling job whose called jobs were all skipped reliably for `needs`.

With `audit: true`, the packages in `uv.lock` are audited once more, for a vulnerability that became known between the merge and the release. The inputs `workflow`, `branch` and `wait-minutes` change which CI workflow and branch count and how long the gate waits.

## Release tags

A release tag is `v` followed by the version exactly as the version file of the project writes it. Every action compares the two as text, so the rule holds for any language, and a tag in another spelling stops the release before anything is published.

A Python project writes its versions as PEP 440 does and tags `v1.2.3`, `v1.0.0rc1` or `v1.2.3.post1`, never `v1.0.0-rc.1`. A project in another language tags in its own format, for example `v1.0.0-rc.1` for semver. Only `publish/ghcr` reads the version itself, to derive the image tags. Its input `version-scheme` is `pep440` by default and `semver` for other projects. A pre-release gets its exact version as image tag, no `1.2` and no `latest`.

A published tag cannot be deleted or moved, see [Repository settings](repository-settings.md#release-tags). A failed release is fixed with a new version, which PyPI asks for anyway.

## Trial runs

A manual run of `publish.yml` tries the image half: `publish/ghcr` builds and pushes `edge`, from the default branch only, since `edge` is public. `publish/pypi` with `dry-run: true` builds and checks everything but the version and asks PyPI whether it would take the files, without uploading and without credentials. If the version is on PyPI already, it warns without failing, since a trial usually runs before the version is raised.

The PyPI trial runs in a job of its own, `pypi-trial` in the example, without the environment and without `id-token: write`. Run in the upload job instead, every manual run would show up as a deployment of the PyPI environment and get an OIDC token it does not need. The upload job keeps `if: github.event_name == 'release'`, so it never runs by hand.

## One-time setup

- PyPI: a pending publisher per project, with the owner, the repository, the workflow file name `publish.yml` and the environment named in the job. PyPI takes a pending publisher for one project only, hence one environment per package.
- GitHub: that environment under Settings, Environments, open to tags `v*` only, see [Repository settings](repository-settings.md#environments).
- ghcr.io: a new package is private even in a public repository. After the first push, switch it to public under the organisation's Packages.
- MCP Registry: nothing. The registry grants `io.github.benethos-hub/*` to the OIDC token of the workflow.
