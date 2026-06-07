# directory-mcp

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

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone <your-fork-url> directory-mcp
cd directory-mcp
uv sync
```

Verify it works:

```sh
uv run pytest        # the full suite
uv run python mcp_server.py   # starts the stdio server (Ctrl-C to stop)
```

## Register with Claude Code

Add it as a user-scoped MCP server so it's available in every session:

```sh
claude mcp add directory -- uv run --directory /absolute/path/to/directory-mcp python mcp_server.py
```

The database is created on first run at `~/.local/share/directory-mcp/directory.db`.
Override with the `DIRECTORY_DATABASE_URL` environment variable (or a `.env` file in the
project root) if you want it elsewhere.

## Using it

The tool surface is deliberately thin — verbs that read like intentions, never the schema
underneath.

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
- `remember_person(name, email?, slack_id?, jira_account_id?, title?, links?, notes?)` —
  record a person; collapses onto an existing one that shares the email, so re-recording is
  safe. Use `links=[{"system","ref_type","value"}]` for any system the named args don't
  cover (e.g. GitHub, Notion, Linear).
- `remember_project(name, jira_keys?, slack_channels?, repos?, links?, notes?)` — a project
  with however many coordinates it sprawls across.
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

## Visualizing your directory

```sh
uv run python scripts/graph/build_graph.py
```

This renders your live database to a standalone `scripts/graph/directory-graph.html` — an
interactive vis-network graph you can open in a browser. From within Claude Code you can do
the same with the bundled `/directory-graph` slash command, which renders and opens it for
you. **The rendered HTML is gitignored — it's a full dump of your directory and should never
be committed.**

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
