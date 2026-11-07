# The findings between the freshness jobs

Every job of `freshness.yml` that measures something leaves an artifact named `freshness-<job>` with up to three files. The report job reads all of them and knows nothing else. A job for another language, or a job of the calling repository, writes the same files and needs no change in the report.

| File | Required | Holds |
| --- | --- | --- |
| `status.json` | yes | Whether the job has a result, and which issue it addresses. |
| `findings.jsonl` | no | One finding per line, for the tables of the report. |
| `section.md` | no | Prose of the job, for what no table can say. |

The name after `freshness-` is the name of the job as the report uses it, in the line about a job without a result, in the `Checks` block and over its section. A job that runs several times, once per project folder or once per package, appends one suffix per run: the folder or the package with every character that is no letter or digit replaced by `-`, so `tools/audit` becomes `freshness-outdated-tools-audit`. The root folder and an unnamed package keep the plain name. The report expects the names the workflow lists in `expected`, suffixes included, and reads every other `freshness-*` artifact it finds as well.

## status.json

One object that says whether the job has a result.

```json
{"result": "ok", "checked": 37, "packages": ["example-service", "example-client"]}
```

| Field | Meaning |
| --- | --- |
| `result` | `ok` when the job measured everything it set out to measure. `inconclusive` when it ran but could not prove anything, after a rate limit or an unreachable counterpart, say. Anything else counts as failed. |
| `checked` | How many pins the job looked at. Informational. |
| `packages` | Optional. The packages of the repository, for a job that knows them. The report shows a packages column once more than one is named. |
| `issue` | Optional. `report`, the default, or `alarm`. The findings and the section of an `alarm` job go to the alarm issue, which the caller names with `alarm-title`. |
| `summary` | Optional. One sentence about what the job checked, names and versions allowed, no log. The report lists it under `Checks`, whatever issue the job addresses, and appends it to the line of a job without a result as the reason. A summary alone never opens the issue. |

A job that is expected and leaves no artifact, an artifact without `status.json`, or a status with a `result` other than `ok` or `inconclusive` is reported as a job without a result. The report is then never empty, so a run that proved nothing cannot close an open issue. A job the caller switched off is not expected and leaves nothing. A job of the calling repository is expected once the caller lists it in `extra-jobs`.

The alarm issue is touched only when every job is conclusive: no job `inconclusive`, no `alarm` job failed, no expected job without an artifact, whose issue would be unknown. Otherwise the alarm issue is left as it was, and the report says which job could not prove anything.

## findings.jsonl

One JSON object per line, one line per finding. A pin that occurs in several files is one finding with every file in `where`. Fields that do not apply to a finding are left out.

```json
{"category": "package", "name": "mcp", "where": ["uv.lock"], "current": "2.3.0", "newest": "2.4.0", "within_bounds": false, "direct": true, "scope": "runtime", "packages": ["example-service"]}
{"category": "package", "name": "hatchling", "where": ["pyproject.toml", "packages/a/pyproject.toml"], "current": "1.33.0", "newest": "1.34.0", "scope": "build"}
{"category": "package", "name": "pip-audit", "where": ["tools/audit/uv.lock"], "current": "2.9.0", "newest": "2.10.0", "within_bounds": true, "direct": true, "scope": "runtime"}
{"category": "image", "name": "python:3.15-slim", "where": ["containers/a/Dockerfile", "containers/b/Dockerfile"], "current": "sha256:8c13a3f3", "newest": "sha256:9d2e7b10", "kind": "rebuild"}
{"category": "image", "name": "python", "where": ["containers/a/Dockerfile"], "current": "3.15-slim", "newest": "3.16-slim"}
{"category": "action", "name": "actions/checkout", "where": [".github/workflows/ci.yml"], "current": "v7.0.1", "newest": "v7.1.0"}
{"category": "vulnerability", "name": "example", "where": ["uv.lock"], "current": "1.0.0", "vulnerability": "GHSA-xxxx-xxxx-xxxx", "fix": ["1.0.1"], "direct": false, "scope": "runtime"}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `category` | yes | `package`, `image`, `action` or `vulnerability`. Decides the section of the report. |
| `name` | yes | What is pinned, as the report names it. |
| `where` | yes | The files that hold the pin, relative to the repository. A job that runs in a project folder names the file with that folder, as `tools/audit/uv.lock`. |
| `current` | yes | The pinned version, tag, digest or commit. |
| `newest` | for all but `vulnerability` | The newest version the job found. |
| `kind` | no | `major`, `minor`, `patch`, `rebuild` or `unknown`. Left out, the report derives it from `current` and `newest`. A job sets it when the two are no version numbers, as for a digest. |
| `within_bounds` | no | Whether `newest` lies inside the bounds the repository allows. Measured by the resolver of the ecosystem. |
| `direct` | no | Whether the repository names the package itself. Left out, the report treats the finding as direct. |
| `scope` | no | `runtime`, `dev` or `build`. A package needed at runtime and in development is `runtime`. Left out when the job does not know it, which reads as runtime. |
| `packages` | no | The packages of the repository that need the finding at runtime. |
| `vulnerability` | for `vulnerability` | The advisory ID. |
| `fix` | no | The versions that fix the advisory. |

A line the report cannot read, a missing `where` or an unknown `category`, say, fails the report job with the line in the error. A job writes what it knows and leaves the rest out, rather than guessing a value.

## section.md

Markdown the report takes over as it is, under a heading with the name of the job, after the tables and the `Checks` block. It is for what no finding can say, such as which step of a check failed on which versions. A job may leave `status.json` and `section.md` alone, without findings. The issue is public: names, versions and the result of a step go in, no log, no secret. Headings inside the section start at the fourth level, the heading with the name of the job is the third.

## How the report derives the kind

The kind compares the numbers in `current` and `newest`, a leading `v` or a suffix like `-slim` is ignored. A different first number is `major`, a different second number is `minor`, any other difference is `patch`. A version that looks like a date, with a first number of four digits or any number of eight digits, is `unknown`, so a new `2026.5.4` never reads as a minor. A digest or a commit, hexadecimal, is `unknown` as well, and so are two values without numbers.

## What the report lists

The tables come first, one per section that has a finding: known vulnerabilities, images, actions, build backends, packages and, on request, development packages. Then a block `Checks` lists the summary of every job with a result that has one, so the pins issue says that a check passed on the newest versions the same day. Each line starts with ✅. An `alarm` job that named a finding or left a section gets a line with ❌ instead, which points to its section or its findings and repeats neither. The line of a job without a result starts with ❌, or with ⚠️ when the job ran but could not prove anything. Then the sections of prose, each under the name of its job. A last paragraph counts what is not named and says what is measured and what is derived.

Named one by one: every vulnerability, image and action, every build backend, every direct runtime package and every major of a runtime package. Only counted: transitive runtime packages that moved by a minor, a patch or an unknown kind. They do not open the issue by themselves. Packages with scope `dev` are hidden and counted, unless the caller asks for them. A finding whose name matches a pattern of the caller's `ignore` input is dropped and counted.

The report is empty, which closes the issue, exactly when nothing is named one by one, no job left a section, and every expected job has a result. The alarm file is empty exactly when no `alarm` job named a finding or left a section. The lines about jobs without a result and the `Checks` block belong to the report alone and never to the alarm file.
