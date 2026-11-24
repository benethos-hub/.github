# Freshness: another language

Part of [FRESHNESS.md](../FRESHNESS.md).

## Another language

The jobs `images`, `actions` and the report know no language. The jobs
`outdated`, `audit` and `index` run one step per ecosystem, guarded by
`if: inputs.ecosystem == 'uv'`, and fail with a word for an ecosystem
without a step. A second language adds an adapter action that writes the
files [FORMAT.md](../../actions/freshness/report/FORMAT.md) describes,
and one such step per job. The report needs no change.

The actions behind the jobs, each usable on its own:

| Action | Knows |
| --- | --- |
| [python/freshness-outdated](../../actions/python/freshness-outdated/action.yml) | `uv.lock`, `pyproject.toml`, `uv lock --upgrade --dry-run` and `uv tree --outdated --universal`, in the folder named by `directory` |
| [python/freshness-audit](../../actions/python/freshness-audit/action.yml) | `uv export` in the folder named by `directory` and the pip-audit action with `findings` |
| [python/freshness-index](../../actions/python/freshness-index/action.yml) | `uv venv`, `uv pip install` from the index, `uv pip freeze` and the check of the repository |
| [python/freshness-newest](../../actions/python/freshness-newest/action.yml) | `uv lock --upgrade` in the runner, `uv sync`, the tests and the check of the repository. A job of the repository, not of the workflow. |
| [node/freshness-outdated](../../actions/node/freshness-outdated/action.yml) | `package-lock.json` and the list of versions on the npm registry, in the folder named by `directory`. A job of the repository, not of the workflow. |
| [node/freshness-audit](../../actions/node/freshness-audit/action.yml) | `npm audit` from the `package-lock.json` in the folder named by `directory`. A job of the repository, not of the workflow. |
| [freshness/images](../../actions/freshness/images/action.yml) | Dockerfiles, YAML files and the registry API, read anonymously as `docker pull` does |
| [freshness/actions](../../actions/freshness/actions/action.yml) | `uses:` lines and the GitHub API |
| [freshness/report](../../actions/freshness/report/action.yml) | Only the files per job |

The registry of Docker Hub counts anonymous reads against the address of
the runner, which is shared. A run asks it for one or two manifests,
which has been enough so far.
