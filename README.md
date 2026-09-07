# directory-mcp

[![Release](https://img.shields.io/github/v/release/ePaint/directory-mcp?sort=semver)](https://github.com/ePaint/directory-mcp/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A private address book for your AI coding agent. It remembers the people, projects and
teams you work with — and where each of them lives in the tools you use (Slack, Jira, GitLab,
GitHub, Outlook, Notion, …) — so when you say *"check what my boss said in the payments
thread"*, your agent already knows who your boss is and where to look, instead of asking you
every time.

Everything stays in one small file on your machine. Nothing is shared or uploaded.

## Install

### Requirements

You need three free tools installed. If you already have them, skip ahead.

- **[Claude Code](https://code.claude.com/docs/en/quickstart)**
- **[git](https://git-scm.com/downloads)** — on a Mac, typing `git` in the terminal offers to
  install it; on Windows, run the installer and accept the defaults.
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — one command, shown at
  the top of that page.

No accounts or sign-ups needed.

### Two commands

In a terminal:

```sh
claude plugin marketplace add https://github.com/ePaint/directory-mcp.git
claude plugin install directory-mcp@directory-mcp
```

The first tells Claude Code where the plugin comes from (you only ever do this once); the
second installs it. Then start a new Claude Code session — or run `/reload-plugins` if the
install output asks you to. The very first start takes a few extra seconds while it sets
itself up.

That's it. Everything below this point is optional.

### Updating, pausing, removing

- **Update**: `claude plugin update directory-mcp`
- **Turn off / on** without uninstalling: `claude plugin disable directory-mcp` /
  `claude plugin enable directory-mcp`. To turn it off for just one project, run the same
  command inside that project with `--scope project` added.
- **Uninstall**: `claude plugin uninstall directory-mcp`, then
  `claude plugin marketplace remove directory-mcp`.

## Getting started

You never operate the directory directly — you talk to your agent, and it does the
bookkeeping. Two things to do first:

1. **Tell it who you are**, so *"my boss"* and *"my team"* mean something:
   *"set me as Ada Lovelace, ada@example.com"*.
2. **Add some people.** Say *"add my teammate Alex"*, or run `/directory-enroll` to add a
   batch — everyone in this week's meetings, say. It finds each person across the tools your
   agent is connected to, asks you the one thing only you know (how they relate to you), and
   saves them.

From then on, just ask: *"who's my boss?"*, *"what's the Slack handle of the person who owns
checkout?"*, *"graph my org"*.

## What's included

- **The directory itself**, available to your agent in every session.
- **A standing instruction** ([`directory-rule.md`](directory-rule.md)) that goes into every
  session, telling the agent to look people up here *before* asking you, to check every
  place the directory points to, and to save new people and relationships as it learns them.
  Turn the plugin off and the instruction goes with it.
- **Two skills**:
  - `/directory-enroll` — add one person or a whole roster, as described above.
  - `/directory-graph` — draw your directory as an interactive graph and open it in the browser.

## Where your data lives

- Your directory is one file: `~/.local/share/directory-mcp/directory.db`. To keep it somewhere
  else, set the `DIRECTORY_DATABASE_URL` environment variable.
- There is no server to sign in to and nothing leaves your machine. Only your own agent, on
  your own computer, can read it.
- Treat the file as you would your contacts: it accumulates names, roles and handles of the
  people you work with.

---

The rest of this page is for people who want to know how it works or wire it up by hand.

## How it works

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

### How disambiguation works

The `interaction` log is what makes ambiguous lookups resolve sensibly. For *"alex from the
acme project"*, candidates are ranked **connection-first**: the Alex actually linked to a
matching Acme wins. Connection is the confidence gate — exactly one connected candidate
gives a confident answer; two or more set `ambiguous: true` and return *all* of them.
Activity (how recently/often something is touched) only orders the best guess; it never
silently drops a candidate. The agent consuming the result decides.

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

## Manual install (no plugin)

If you'd rather not use plugins, wire the three pieces up individually:

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

Safe to re-run, e.g. after you move the repo (the `/directory-graph` skill records where the
checkout is). Start a new Claude Code session afterwards. Pass `--no-rule` (PowerShell:
`-NoRule`) to install only the skills and leave your `CLAUDE.md` untouched.

The installer copies the skills to `~/.claude/skills/` (honoring `CLAUDE_CONFIG_DIR` if set),
copies the rule to `~/.claude/directory-rule.md`, and adds a single `@./directory-rule.md`
import line to your `~/.claude/CLAUDE.md` between markers, so re-running won't duplicate it
(re-running also migrates older installs that inlined the whole rule). To scope the rule to one
repo instead, inline the snippet into that project's `CLAUDE.md` — an import won't work there,
because project-level imports that resolve outside the project directory are silently skipped.

Because the rule is one imported file, it toggles without editing `CLAUDE.md`:

- **Globally** — `./install.sh --disable` / `--enable` (PowerShell: `-Disable` / `-Enable`).
  This renames the rule file aside; Claude Code skips a missing import silently.
- **Per project** — exclude the file in that project's `.claude/settings.json` (or
  `settings.local.json`), which catches `@`-imported files too:

  ```json
  { "claudeMdExcludes": ["**/directory-rule.md"] }
  ```

Manual uninstall:

```sh
./install.sh --uninstall     # PowerShell: .\install.ps1 -Uninstall
claude mcp remove directory
```

The first command removes the skills, the rule file and the `CLAUDE.md` import block; the
server registration is separate, so remove it with the second.

## License

[MIT](LICENSE).
