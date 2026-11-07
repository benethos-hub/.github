# Reports in an issue

[actions/report-issue](../actions/report-issue/action.yml) keeps the result of a scheduled workflow in one open issue, in any repository and for any language. A run with something to report opens the issue or replaces its body. A run with nothing to report closes it. Before that it puts a line at the top of the body that says when and why, so the report beneath it reads as the last one before the close and not as the current state.

```yaml
name: Daily check

on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

permissions:
  contents: read
  issues: write

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@<sha> # vX

      - name: Check
        run: ./check.sh > "$RUNNER_TEMP/report.md"

      - name: Update the issue
        uses: benethos-hub/.github/actions/report-issue@main
        with:
          title: The daily check found something
          report: ${{ runner.temp }}/report.md
          resolved: The daily check found nothing.
```

| Input | What it does |
| --- | --- |
| `title` | The title of the issue. The open issue with exactly this title is the one kept. |
| `report` | The Markdown file with the report. An empty file means there is nothing to report. |
| `resolved` | One sentence for a run with nothing to report. It goes to the step summary and closes the issue as a comment. |
| `token` | The token for the GitHub CLI. The default is the token of the workflow, which needs `issues: write`. |

The check writes nothing to the file when all is well, and only the report when it is not. If the check step itself fails, the job stops before this action and the issue stays as it was.

The action adds a line to the body that links to the calling workflow. It looks at the newest 100 open issues. A changed title opens a new issue and leaves the old one open.

`brand-report.yml` and `download-pins-report.yml` of this repository use it as well, by local path after the checkout, and so does the [freshness report](freshness.md) of every repository.
