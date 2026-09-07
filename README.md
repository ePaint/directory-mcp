# directory-mcp

[![Release](https://img.shields.io/github/v/release/ePaint/directory-mcp?sort=semver)](https://github.com/ePaint/directory-mcp/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A **local, single-user directory** for your AI coding agent: a consolidation layer that
records the people, projects, teams and artifacts you work with — and their coordinates
across every system you use (Slack, Jira, GitLab, GitHub, Outlook, Notion, …).

It exists to answer one kind of question well. When you tell your agent *"check what my
boss said in the payments thread"*, the agent needs to turn "my boss" into a real person,
and that person into the exact Slack id (or Jira account, or email) to hand to your other
MCP servers. `directory-mcp` is the thing that remembers all of that, so the agent doesn't
have to ask you every time.

It is **not** a shared service. It's a SQLite file on your machine, for your agent only.

## Why a graph instead of tables

Real orgs are messy: a project sprawls across many Jira keys, scattered Slack channels and
several repos; people change teams; clients have sub-projects. So there are no rigid
per-system columns. Everything is one of five shapes:

| Shape | What it is |
| --- | --- |
| `entity` | Any node — a person, project, team, org, or artifact. `kind` is open text. |
| `anchor` | An external coordinate of an entity (`system`, `ref_type`, `value`). Many per entity. This is the resolver. |
| `edge` | A directed, free-text relationship (`reports_to`, `member_of`, `works_on`, …). |
| `observation` | An atomic, sourced fact; an optional `key` makes it a semi-structured attribute. |
| `interaction` | An append-only usage log. Recency/frequency are *derived*, never stored as counters. |

Messiness becomes more rows, never a schema migration. `system` / `ref_type` / `kind` /
relation type are all **open vocabulary** — writes are normalized toward canonical forms
(so `Reports-To`, `reports-to` and `reportsto` all collapse to `reports_to`), but unknown
values are kept, never rejected. Use whatever MCPs you use; the directory adapts.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/) ([install uv](https://docs.astral.sh/uv/getting-started/installation/)).

### As a Claude Code plugin (recommended)

One install wires up all three pieces — the MCP server, both [bundled skills](#bundled-skills),
and the [proactive-use rule](#make-your-agent-reach-for-it), injected into every session by a
SessionStart hook:

```sh
claude plugin marketplace add https://github.com/ePaint/directory-mcp.git
claude plugin install directory-mcp@directory-mcp
```

The first command registers this repo as a plugin marketplace (a one-time step; there is no
central registry to install from directly), the second installs the plugin from it. The HTTPS
URL works without GitHub SSH keys; the shorthand `ePaint/directory-mcp` clones over SSH. A local
clone's path works too. If the install summary says `Run /reload-plugins to activate`, do that,
or start a new Claude Code session.

The first session runs `uv sync` for the server's dependencies, so the `directory` server takes
a few seconds longer to connect once. The database is created on first run at
`~/.local/share/directory-mcp/directory.db`; override with the `DIRECTORY_DATABASE_URL`
environment variable if you want it elsewhere.

Update later with `claude plugin update directory-mcp`.

Toggle it without uninstalling — this turns the server, the skills and the rule off together:

- **Globally**: `claude plugin disable directory-mcp` / `claude plugin enable directory-mcp`.
- **Per project**: the same commands with `--scope project` (shared via the project's
  settings) or `--scope local` (personal, untracked), run inside that project.

Uninstall: `claude plugin uninstall directory-mcp`, then
`claude plugin marketplace remove directory-mcp`.

### Manual install (no plugin)

If you'd rather not use plugins, wire the pieces up individually:

```sh
git clone https://github.com/ePaint/directory-mcp.git
cd directory-mcp
uv sync
claude mcp add directory -- uv run --directory /absolute/path/to/directory-mcp python mcp_server.py
```

Then run the installer for the skills and the rule:

```sh
./install.sh         # macOS / Linux / Git Bash / WSL
```

```powershell
.\install.ps1        # Windows PowerShell
```

It's idempotent — safe to re-run, e.g. after you move the repo (the skill bakes in an
absolute path to this checkout). Start a new Claude Code session afterwards to pick everything
up. Pass `--no-rule` (PowerShell: `-NoRule`) to install only the skills and leave your
`CLAUDE.md` untouched.

Manual uninstall:

```sh
./install.sh --uninstall     # PowerShell: .\install.ps1 -Uninstall
claude mcp remove directory
```

The first command removes the skills, the rule file and the `CLAUDE.md` import block; the
server registration is separate, so remove it with the second. To merely turn the rule off
without uninstalling, see [toggling](#make-your-agent-reach-for-it).

## Getting started

You drive the directory through your agent in plain language — it calls the tools for you.
Two things to do first:

1. **Tell it who you are**, so self-relative phrases like *"my boss"* resolve: *"set me as
   Ada Lovelace, ada@example.com"* → `set_self`.
2. **Enroll some people.** The bundled [`/directory-enroll`](#bundled-skills) skill finds a
   person across your connected MCPs, asks how they relate to you, and records them. Or just
   ask: *"add my teammate Alex"*.

After that, ask things like *"who's my boss?"*, *"what's the Slack id for the person who
owns checkout?"*, or *"graph my org"* — and the agent resolves them against the directory.

## Make your agent reach for it

The server ships usage `instructions` that Claude Code surfaces automatically — but the
strongest signal is [`directory-rule.md`](directory-rule.md) in your session context: resolve
any person/project against the directory *first*, never ask who someone is if the directory
knows, follow through on every anchor it returns, and capture handles/relationships as you
work.

**Plugin install**: a SessionStart hook injects the rule into every session (re-firing on
resume, clear and compact), so there is nothing to wire up — disable the plugin and the rule
goes with it.

**Manual install**: the installer copies the rule to `~/.claude/directory-rule.md` and adds a
single `@./directory-rule.md` import line to your `~/.claude/CLAUDE.md`, between markers so
re-running won't duplicate it (re-running also migrates older installs that inlined the whole
rule). To scope it to one repo instead, inline the snippet into that project's `CLAUDE.md` —
an import won't work there, because project-level imports that resolve outside the project
directory are silently skipped.

Because the manually installed rule is one imported file, it toggles without editing
`CLAUDE.md`:

- **Globally** — `./install.sh --disable` / `--enable` (PowerShell: `-Disable` / `-Enable`).
  This renames the rule file aside; Claude Code skips a missing import silently.
- **Per project** — exclude the file in that project's `.claude/settings.json` (or
  `settings.local.json`), which catches `@`-imported files too:

  ```json
  { "claudeMdExcludes": ["**/directory-rule.md"] }
  ```

## Bundled skills

The repo ships two [Claude Code skills](https://docs.claude.com/en/docs/claude-code/skills)
under `skills/`. The plugin exposes them everywhere automatically (namespaced, e.g.
`directory-mcp:directory-graph`). The manual installer instead copies both to
`~/.claude/skills/` (honoring `CLAUDE_CONFIG_DIR` if set) and rewrites `/directory-graph` to
point its renderer at this checkout so it works from any working directory.

- **`/directory-enroll`** — turn a name (or a roster, like everyone in this week's meetings)
  into directory entries. It resolves each person across whatever people-search MCPs you have
  connected, collapses duplicates by email, asks you the one thing only you know (the
  relationship), and records it. MCP-only, so it works from anywhere.
- **`/directory-graph`** — render your directory to an interactive graph and open it in the
  browser. It runs the bundled renderer (`scripts/graph/build_graph.py`); the installer points
  it at this checkout, so once installed it works from anywhere.

## Tool reference

The tool surface is deliberately thin — verbs that read like intentions, never the schema
underneath. Your agent picks these for you; you rarely name them directly.

**Look up** (read):

- `whois(query)` — resolve a person/project by name, email, or a self-relative phrase like
  `"my boss"` / `"my team"`; returns who they are, their contacts grouped by system, their
  relationships and recorded facts. Flags `ambiguous` and lists `alternatives` when the
  query matches more than one plausible candidate.
- `who_to_query(query)` — just the external coordinates, grouped by system, ready to feed
  your other MCPs.
- `find(query, kind?)` — search by name, optionally narrowed by kind.
- `vocab()` — the canonical suggested values plus what's already in use.

**Capture** (write):

- `set_self(name, email)` — mark the connected user. This is the anchor for resolving
  `"my boss"` / `"my team"` by walking edges.
- `remember_person(name, email?, title?, links?, notes?)` — record a person; collapses onto
  an existing one that shares the email, so re-recording is safe. `email` is the identity key;
  attach every other coordinate via `links=[{"system","ref_type","value"}]` (Slack, Jira,
  GitHub, Notion, anything — no system is privileged).
- `remember_project(name, links?, notes?)` — a project with however many coordinates it
  sprawls across, each given as a `links` entry.
- `remember_team(name)` / `remember_org(name)` — grouping entities for `member_of` edges.
- `relate(subject, relation, target)` — record a relationship, e.g.
  `relate("alice@example.com", "reports_to", "bob@example.com")`. Idempotent.
- `link(subject, system, ref_type, value)` — attach any coordinate to an existing entity.
- `note(subject, fact, key?)` — attach a fact; set `key` for a semi-structured attribute.
- `record_reference(kind, system, ref_type, value, title?, people?, role?)` — record an
  artifact (a thread, ticket, email, doc) and the people on it, in one call. Idempotent on
  its coordinate.
- `tag(subject, label)` / `find_by_tag(label)` — lightweight tagging.
- `merge(keep, drop)` — fold a duplicate entity into another.

### How disambiguation works

The `interaction` log is what makes ambiguous lookups resolve sensibly. For *"alex from the
acme project"*, candidates are ranked **connection-first**: the Alex actually linked to a
matching Acme wins. Connection is the confidence gate — exactly one connected candidate
gives a confident answer; two or more set `ambiguous: true` and return *all* of them.
Activity (how recently/often something is touched) only orders the best guess; it never
silently drops a candidate. The agent consuming the result decides.

## Privacy & scope

- **Single-user and local by design.** The server speaks stdio to one local agent. There is
  no network listener and no authentication, because there is nothing multi-tenant to
  authenticate — it points at *your* SQLite file and no one else's.
- The database lives outside the repo (`~/.local/share/directory-mcp/`) and is gitignored as
  a backstop, along with the rendered graph and any `.env`.
- Treat the database as you would your contacts: it accumulates names, roles and
  cross-platform handles of people you work with.

## License

[MIT](LICENSE).
