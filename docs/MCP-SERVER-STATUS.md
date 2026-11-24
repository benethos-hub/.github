# The MCP tool server_status

Every MCP server of the organisation offers one tool, `server_status`,
with the same shape. This page is its convention. It was decided on
2026-10-29. Later changes are listed at the end with their date.

## Why

The MCP servers of the organisation answer the same question, "what is
running and is it well?", each in its own way or not at all. Claude
Desktop shows neither the server's version nor whether its upstream
answers, and a model cannot read the `serverInfo` of the handshake. One
tool with one shape, in every server, lets a person ask in the chat and
lets a model explain why a tool is missing.

## A. The tool

1. **Name `server_status`**, spelled the same in every server. Title
   "Server status". Hints: `readOnlyHint: true`, and
   `openWorldHint: false` where the tool asks no one or only its own
   known upstream. The MCP specification gives `destructiveHint` and
   `idempotentHint` a meaning only for tools that are not read-only, so
   they are left out. Anything else the project decides.
2. **Always offered**: without a right, without a reachable upstream,
   without a token the upstream accepts. It is the one tool that is
   there when the server offers nothing else.
3. **One parameter, `details`**, boolean, default `false`. A second
   parameter only when a project needs it in the details part and it
   does something. A parameter that does nothing is not allowed.
4. **Description in two sentences**: what the quick answer says, what
   `details` adds. Every tool sits in every chat's context.
5. **The tool never fails.** Every trouble is a field value. No
   exception reaches the client. A server that cannot answer its own
   status tool has a bug.

## B. The answer

6. **Plain text, one field per line, `key: value`**, no prose. Two
   parts: the core as flat lines, then, with `details: true`, the line
   `details:` without a value and below it the project's blocks as
   objects, each a line `name:` with its fields indented. Two spaces per
   level.
7. **Keys** are lower case, `snake_case`, English, stable in name and
   meaning. **Values**: truth is `yes`, `no` or `unknown`. Durations are
   whole seconds with the unit in the key (`uptime_seconds`). Points in
   time read as "n seconds ago" (`checked_seconds_ago`), never absolute.
   Versions are written as the package names them.
8. **No `structuredContent`** in the first version. When it comes, it
   mirrors the two parts as objects `core` and `details` with the same
   keys, and the text stays.

## C. `details: false`: the core, the same everywhere

9. The core needs neither network nor a request, and its only state is
   the start time of the process. It is answered from memory in
   milliseconds, in this order:

   | Field | Content | Source |
   |---|---|---|
   | `name` | the package name | package metadata |
   | `version` | the server's version | `__version__` |
   | `transport` | the transport as the setting names it (`stdio`, `streamable-http`, `sse`, ...) | the setting |
   | `python` | `major.minor.patch` | `sys.version_info` |
   | `mcp` | the version of the MCP library | package metadata |
   | `uptime_seconds` | since the process started | a monotonic clock, read at start |

10. **The line between core and details**: anything that needs a
    counter, a cache, a remembered answer or a request is state and
    belongs under `details`. The start time is the one exception, named
    here and closed.
11. **No project adds to the core or leaves anything out.** No count of
    tools: the server does not know what a client has switched off.

## D. `details: true`: the project's part

12. The core again, then `details:` and the project's blocks as objects.
    Which blocks exist and what they hold is the project's decision. The
    convention fixes only the form (section B), the shape of an
    `upstream:` block (rule 13), how the upstream's state is learned
    (rules 14, 15) and the rules on secrets (section E).

    A field appears under `details` only where its value can differ,
    between two installations of this server or between two answers of
    one. A field that would read the same everywhere and always says
    nothing and is left out. What is fixed for every server belongs to
    the core, and the core is closed (rule 11).

    Keep `details` minimal. Every field must answer a question a person
    or a model would actually ask when something does not work: is the
    upstream there, is the key good, do the versions match, which tools
    are offered. A field that is merely available is not a reason to
    show it. The answer is read in a chat, and every line costs
    attention. Ten lines that each decide something beat forty that
    describe. When in doubt, leave the field out: adding later is free
    (rule 22), removing is not (rule 24).
13. **Where there is an upstream**, a block `upstream:` comes first with
    `reachable` (`yes`, `no`, `unknown`) and `checked_seconds_ago` (a
    whole number, or `never`). Then comes `token_set` (`yes` or `no`,
    never the value), only where the upstream takes a credential. An
    upstream that takes none would always say `no` (rule 12). Then come
    the project's fields. The fields describe states, never contents:
    whether a key is valid, whether versions match, how much of a rate
    limit is left. Several upstreams, several blocks, each built this
    way.
14. **Two ways to know the upstream's state**, the project picks one.
    Passive: the server reports what its last real request to the
    upstream showed, with the true `checked_seconds_ago`. There is no
    probe and no lock. Active: at most one small request per upstream,
    to its cheapest endpoint, past any cache, under a lock of 30 seconds
    per process. A second `details: true` within the lock makes no
    request and answers with the last result and the true
    `checked_seconds_ago`. A server whose normal work already touches
    the upstream regularly takes the passive way.
15. **A probe never counts as a failed attempt at the upstream and uses
    no rate limit.** An endpoint that counts failures or spends a quota
    is unfit for the probe. A server that knows its upstream refused it
    does not probe again and says so in a field of its block.
16. **A server without an upstream** offers another block, such as
    `local:`, with what can sensibly be checked there as `yes` or `no`
    without a path. If there is nothing to evaluate, the description
    says that `details` adds nothing.
17. **A server whose tools follow rights** names them in its upstream
    block as `tools_offered`, a list of names, and its description says
    that the client may hide some of them. A server with a fixed set of
    tools leaves this out.

## E. Secrets and private data

18. Never a secret or a part of one, not its length, not a hash.
19. No paths, no setting values, only whether something is set. The only
    address allowed is the upstream's, and only when the server names it
    in its start log anyway.
20. No error text of the upstream, ever. Why the upstream is not there
    or not usable is said, if at all, by a field of the project's block
    with a fixed set of values the project documents (`token_valid: no`,
    `rate_limited: yes`, `versions_match: no`), never by quoting what
    the upstream answered.
21. No data of a person: no account name, no address, no search term.

## F. Extensibility

22. **Fields are added, never removed.** New fields go after the
    existing ones of their object.
23. **A field never changes its meaning or format.** When another is
    needed, it gets a new name.
24. Should something have to go after all, the first line reads
    `schema: 2`. Without that line, version 1 applies. A version is
    described on the convention page before any server ships it.
25. **The core grows only through the convention**, then in every
    server. Every block under `details` grows only additively through
    its project.

## G. Building it

26. **A thin tool module** (`tools/status.py` or the project's
    equivalent) collects the fields and formats them. The probe, or the
    passive reading of the last request, lives in the module that
    already talks to the upstream, never in the tool. The project's
    architecture tests get the line for the new module.
27. **The core and the formatting** are the same twenty or so lines in
    every server. They are not shared between projects, since the
    projects share no code. The convention keeps them the same, and each
    project's tests keep them in line.
28. **Logging**: the tool logs nothing at `INFO`. A status question is
    not an activity. A failed probe logs at `DEBUG` at most, since its
    result is in the answer anyway.
29. **Over HTTP** the server's bearer guard stands in front of this tool
    as in front of every other. The tool checks nothing itself.

## H. Tests every project has

30. The core fields by name and order, without network.
31. No secret in the text: a known token value is set, and neither it
    nor a part of it appears in the answer.
32. `details: false` makes no request. Where the project probes (rule
    14, active): `details: true` makes at most one request per upstream,
    and the lock allows no second within 30 seconds. Where it reports
    its last real request (passive): `details: true` makes no request
    either.
33. One test per upstream state the project's fields can show (for
    example `reachable: yes` with `versions_match: yes`,
    `reachable: no`, `token_valid: no`, `versions_match: no`).
34. The tool does not fail when the upstream raises.

## I. Documentation

35. One row in the README's tool table, the entry in the bundle manifest
    and in the registry entry where the project has them, one changelog
    line under Added.
36. Each README names only its own `server_status`. The convention lives
    in `benethos-hub/.github`. No repository names the sibling projects.

## Examples

`details: false`, any server:

```
name: example-mcp
version: 1.4.0
transport: stdio
python: 3.15.2
mcp: 2.3.0
uptime_seconds: 418
```

`details: true`, a server whose upstream is a REST service of the same
organisation, and whose tools follow the token's rights:

```
name: example-mcp
version: 1.4.0
transport: stdio
python: 3.15.2
mcp: 2.3.0
uptime_seconds: 418
details:
  upstream:
    reachable: yes
    checked_seconds_ago: 0
    token_set: yes
    service_version: 1.4.0
    versions_match: yes
    token_valid: yes
    tools_offered: list_accounts, list_folders, search_messages, get_message
```

`details: true`, a server whose upstream is a public data API without a
credential, reporting its last real request (rule 14, passive), while
the API holds it off:

```
name: example-mcp
version: 0.9.2
transport: streamable-http
python: 3.15.2
mcp: 2.3.0
uptime_seconds: 86400
details:
  upstream:
    reachable: yes
    checked_seconds_ago: 17
    rate_limited: yes
```

`details: true`, a server whose upstream is an API behind a key (the
core left out here, it looks as above):

```
details:
  upstream:
    reachable: yes
    checked_seconds_ago: 0
    token_set: yes
    token_valid: yes
    rate_limit_left: 940
```

## Open for each project

- Which blocks `details` holds and which fields each one has (section D,
  rule 13), and whether the upstream is read passively or probed (rule
  14). Decide this before building and name it in the pull request.
- Whether the project needs a second parameter (rule 3). Almost always
  no.
- Where the start time is read (rule 9): the project's main function or
  its server factory, whichever every transport passes through.

## Changes

- 2026-11-24: the field for the key in the last example is called
  `token_valid`, as in rules 20 and 33. It was called `key_valid`
  before.
