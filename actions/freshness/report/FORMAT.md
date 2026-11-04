# The findings between the freshness jobs

Every job of `freshness.yml` that measures something leaves an artifact named `freshness-<job>` with two files. The report job reads all of them and knows nothing else. A job for another language writes the same two files and needs no change in the report.

## status.json

One object that says whether the job has a result.

```json
{"result": "ok", "checked": 37, "packages": ["example-service", "example-client"]}
```

| Field | Meaning |
| --- | --- |
| `result` | `ok` when the job measured everything it set out to measure. Anything else counts as failed. |
| `checked` | How many pins the job looked at. Informational. |
| `packages` | Optional. The packages of the repository, for a job that knows them. The report shows a packages column once more than one is named. |

A job that is expected and leaves no artifact, or leaves a status other than `ok`, is reported as a job without a result. The report is then never empty, so a run that proved nothing cannot close an open issue. A job the caller switched off is not expected and leaves nothing.

## findings.jsonl

One JSON object per line, one line per finding. A pin that occurs in several files is one finding with every file in `where`. Fields that do not apply to a finding are left out.

```json
{"category": "package", "name": "mcp", "where": ["uv.lock"], "current": "2.3.0", "newest": "2.4.0", "within_bounds": false, "direct": true, "scope": "runtime", "packages": ["example-service"]}
{"category": "package", "name": "hatchling", "where": ["pyproject.toml", "packages/a/pyproject.toml"], "current": "1.33.0", "newest": "1.34.0", "scope": "build"}
{"category": "image", "name": "python:3.15-slim", "where": ["containers/a/Dockerfile", "containers/b/Dockerfile"], "current": "sha256:8c13a3f3", "newest": "sha256:9d2e7b10", "kind": "rebuild"}
{"category": "image", "name": "python", "where": ["containers/a/Dockerfile"], "current": "3.15-slim", "newest": "3.16-slim"}
{"category": "action", "name": "actions/checkout", "where": [".github/workflows/ci.yml"], "current": "v7.0.1", "newest": "v7.1.0"}
{"category": "vulnerability", "name": "example", "where": ["uv.lock"], "current": "1.0.0", "vulnerability": "GHSA-xxxx-xxxx-xxxx", "fix": ["1.0.1"], "direct": false, "scope": "runtime"}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `category` | yes | `package`, `image`, `action` or `vulnerability`. Decides the section of the report. |
| `name` | yes | What is pinned, as the report names it. |
| `where` | yes | The files that hold the pin, relative to the repository. |
| `current` | yes | The pinned version, tag, digest or commit. |
| `newest` | for all but `vulnerability` | The newest version the job found. |
| `kind` | no | `major`, `minor`, `patch`, `rebuild` or `unknown`. Left out, the report derives it from `current` and `newest`. A job sets it when the two are no version numbers, as for a digest. |
| `within_bounds` | no | Whether `newest` lies inside the bounds the repository allows. Measured by the resolver of the ecosystem. |
| `direct` | no | Whether the repository names the package itself. Left out, the report treats the finding as direct. |
| `scope` | no | `runtime`, `dev` or `build`. A package needed at runtime and in development is `runtime`. Left out when the job does not know it, which reads as runtime. |
| `packages` | no | The packages of the repository that need the finding at runtime. |
| `vulnerability` | for `vulnerability` | The advisory ID. |
| `fix` | no | The versions that fix the advisory. |

## How the report derives the kind

The kind compares the numbers in `current` and `newest`, a leading `v` or a suffix like `-slim` is ignored. A different first number is `major`, a different second number is `minor`, any other difference is `patch`. A version that looks like a date, with a first number of four digits or any number of eight digits, is `unknown`, so a new `2026.5.4` never reads as a minor. A digest or a commit, hexadecimal, is `unknown` as well, and so are two values without numbers.

## What the report lists

Named one by one: every vulnerability, image and action, every build backend, every direct runtime package and every major of a runtime package. Only counted: transitive runtime packages that moved by a minor, a patch or an unknown kind. They do not open the issue by themselves. Packages with scope `dev` are hidden and counted, unless the caller asks for them. A finding whose name matches a pattern of the caller's `ignore` input is dropped and counted.

The report is empty, which closes the issue, exactly when nothing is named one by one and every expected job has a result.
