# Repository settings

Every repository of the organisation, this one included, has the settings on this page. They live in GitHub, not in the repository, so a new repository needs them set by hand once. Each section names the place in the settings and the call of the GitHub CLI that sets the same, with `<repo>` for the repository.

The organisation is on GitHub Free, which has no organisation rulesets. Every rule is therefore set per repository.

## General

Settings, General:

- Pull requests: allow squash merging and rebase merging, not merge commits, so the history of `main` stays linear.
- Automatically delete head branches.
- Wiki off. The documentation lives in the repository.

```sh
gh api -X PATCH repos/benethos-hub/<repo> --input - <<'EOF'
{"allow_merge_commit": false, "allow_squash_merge": true, "allow_rebase_merge": true,
 "delete_branch_on_merge": true, "has_wiki": false}
EOF
```

## Branch protection

Settings, Branches, a classic branch protection rule for `main`:

- Require status checks to pass, with the checks of the CI as required checks. The branch does not have to be up to date.
- Require conversation resolution.
- Require linear history.
- Do not allow bypassing the above settings, so the rules bind admins as well.
- No force pushes and no deletion.
- No required review. The organisation has one maintainer, who cannot approve their own pull request.

With required checks that bind admins, nothing reaches `main` without a pull request. A check has to have run once in the repository before it can be selected in the settings. The API takes it right away.

The required checks are the names [CI of a Python project](ci.md#check-names) explains. They differ by repository:

| Repository | Required checks |
| --- | --- |
| A Python project | `brand / Brand assets`, `lint / lint`, `test / Python 3.11` to `test / Python 3.15`, `lowest-versions / Python 3.11`, `audit / Dependency audit` |
| With several packages | the above, plus one `lowest-<package> / Python 3.11` per further call of `python-lowest-versions.yml` |
| With a container image | the above, plus the jobs of its own CI that build the image, in the projects `docker` and `fresh-install` |
| This repository | `lint / lint`, `test / Python 3.11` to `test / Python 3.15`, `audit / Dependency audit`, `Lockfiles of the actions` |

A changed job name or Python version changes the check names. The branch protection has to follow in the same step, otherwise it waits for a check that never comes.

```sh
gh api -X PUT repos/benethos-hub/<repo>/branches/main/protection --input - <<'EOF'
{
  "required_status_checks": {"strict": false, "checks": [
    {"context": "brand / Brand assets", "app_id": 15368},
    {"context": "lint / lint", "app_id": 15368},
    {"context": "test / Python 3.11", "app_id": 15368},
    {"context": "test / Python 3.12", "app_id": 15368},
    {"context": "test / Python 3.13", "app_id": 15368},
    {"context": "test / Python 3.14", "app_id": 15368},
    {"context": "test / Python 3.15", "app_id": 15368},
    {"context": "lowest-versions / Python 3.11", "app_id": 15368},
    {"context": "audit / Dependency audit", "app_id": 15368}
  ]},
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
EOF
```

`15368` is GitHub Actions, so a check of the same name from another app does not count.

## Release tags

Settings, Rules, Rulesets, a tag ruleset named `Release tags` in every repository that publishes releases:

- Enforcement status Active, with an empty bypass list.
- Target the tags `refs/tags/v*`.
- Restrict updates and restrict deletions.

A release creates its tag, which the ruleset allows. Afterwards the tag can neither be moved to another commit nor deleted, so a published version always points to the commit it was built from.

```sh
gh api -X POST repos/benethos-hub/<repo>/rulesets --input - <<'EOF'
{
  "name": "Release tags",
  "target": "tag",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
  "rules": [{"type": "deletion"}, {"type": "update"}]
}
EOF
```

## Environments

Settings, Environments, one environment per package on PyPI, named as in the job of `publish.yml`, for example `pypi-benethos-example`. Under Deployment branches and tags, choose Selected branches and tags and add the tag rule `v*`.

The upload jobs run on a release only, whose ref is the tag. The rule makes sure that nothing else can deploy to the environment, not even a manual run on `main`. `pypi-trial` has no environment and is not affected. The one-time setup of PyPI itself is in [Publishing a release](releases.md#one-time-setup).

```sh
gh api -X PUT repos/benethos-hub/<repo>/environments/<environment> --input - <<'EOF'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh api -X POST repos/benethos-hub/<repo>/environments/<environment>/deployment-branch-policies \
  -f name='v*' -f type=tag
```

## Security

Settings, Advanced Security:

- Dependabot alerts and Dependabot security updates on.
- Secret scanning and push protection on.
- Private vulnerability reporting on. The [security policy](../SECURITY.md) asks for reports through it, and the button only appears when it is on.

```sh
gh api -X PUT repos/benethos-hub/<repo>/vulnerability-alerts
gh api -X PUT repos/benethos-hub/<repo>/automated-security-fixes
gh api -X PUT repos/benethos-hub/<repo>/private-vulnerability-reporting
gh api -X PATCH repos/benethos-hub/<repo> --input - <<'EOF'
{"security_and_analysis": {"secret_scanning": {"status": "enabled"},
 "secret_scanning_push_protection": {"status": "enabled"}}}
EOF
```

## Actions

Settings, Actions, General, Workflow permissions: read repository contents and packages, and do not allow GitHub Actions to create or approve pull requests. Every job asks for what it needs beyond that in its own `permissions:`. Every repository has these settings today. Check them in a new one.

```sh
gh api -X PUT repos/benethos-hub/<repo>/actions/permissions/workflow \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
```

## Dependabot

Every repository has a `.github/dependabot.yml` with one entry per ecosystem it uses: `uv` for `uv.lock`, `github-actions` for the pinned actions, and `docker` for each folder with a Dockerfile. Each entry runs weekly and groups minor and patch updates into one pull request, so a major update comes on its own:

```yaml
    groups:
      minor-and-patch:
        patterns: ["*"]
        update-types: ["minor", "patch"]
```

This repository runs every entry daily. The repositories call its workflows and actions at `main`, so an update here reaches all of them on the same day, and only the Dependabot of this repository keeps those pins current.

Dependabot takes daily as Monday to Friday, and it proposes a release only once it is three days old. It waits that long without being told. This repository writes the wait down as `cooldown` with `default-days: 3`, so the file shows what happens.

A package whose updates need a review of their own, such as the `mcp` SDK in the MCP servers, is left out of the group through `exclude-patterns`, so each of its updates is a pull request of its own. The `dependabot.yml` of [lexware-office-mcp](https://github.com/benethos-hub/lexware-office-mcp/blob/main/.github/dependabot.yml) shows all three entries with the reason for each.
