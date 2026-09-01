# CLAUDE.md — directory-mcp

Local, single-user directory MCP. A consolidation layer that records people, projects and
artifacts and their cross-platform references (Slack / Jira / GitLab / Outlook / GitHub / … —
`system` is open vocab, not a fixed set), so a local Claude Code instance can resolve "check
what my boss said" to a person, their relationships, and the exact external coordinates needed
to query the other MCPs. SQLite, no shared service.

## Core model — a flexible graph, NOT rigid per-kind tables

Real orgs are messy: a project has many Jira keys, scattered Slack channels, several repos,
sub-projects. So there are no typed columns like `jira_project_key`. Four shapes only:

- `entity` — every node. `kind` is open vocab (person/project/team/org/artifact/resource).
- `anchor` — external coordinate, MANY per entity. `(system, ref_type, value)`. The resolver.
- `edge` — every relationship, free-text `type`. Org graph, membership, sub-projects, references.
- `observation` — atomic sourced fact; optional `key` makes it a semi-structured attribute.
- `interaction` — append-only usage log `(entity_id, kind, at)`. Count + last-seen are DERIVED,
  never stored as mutable counters. This is the recency signal that disambiguates ambiguous
  lookups ("alex from the acme project" → the Acme project we keep touching, not the 2024 one).

Messiness becomes more rows, never a schema change. This is Anthropic's entity/relation/
observation memory model plus a universal anchor layer. The MCP tool surface stays THIN
(verbs like whois / record / relate) so agents never reason about tables.

## Conventions (mirrors a sibling MCP; code-structure-like-me + code-like-me)

- Bounded context = package with `api.py` (public) + `internal/` (hidden). Import only `api.py`.
- One cohesive `DirectoryStore`: `Protocol` + `InMemoryDirectoryStore` + `SqlAlchemyDirectoryStore`,
  exercised by ONE parametrized `memory`/`sql` test fixture so the double can't drift.
- SQLAlchemy `DeclarativeBase`; the store owns its schema via `create_all` (no Alembic — it is a
  rebuildable index, not a system of record). Sync SQLAlchemy runs in `asyncio.to_thread`.
- `build_*` factories, constructor/keyword injection, keyword-only internal args.
- Name search is a `search_text` column + LIKE (no FTS), like the sibling MCP.
- Comments explain WHY only. Tests mirror source under `tests/`.

## Landmines

- Open vocab, not enums: `kind` / `system` / `ref_type` / edge `type` are free strings so a new
  system or relationship never needs a migration. Keep a suggested-values constant for consistency.
- Identity collapse is policy, not storage: the store is mechanical (`entity_by_anchor`); the
  email-primary-key auto-collapse + manual `merge_entities` decision lives in the layer above.
- `is_self` marks the connected user — the anchor for "my boss" / "my team" edge traversal.
- CLAUDE.md `@import` (all verified empirically 2026-09-01): user-level `~/.claude/CLAUDE.md`
  imports sibling files fine (relative, `~`, absolute), but a PROJECT-level CLAUDE.md silently
  skips imports that resolve outside the project dir — so the installed rule import only works
  at user level. A missing import is skipped silently (what `--disable` relies on), and
  `claudeMdExcludes` in settings.json matches `@`-imported files (the per-project off switch).

## Status

Phases 1–2 done: `DirectoryStore` (entity/anchor/edge/observation); `directory/resolve.py`
`Directory` facade (whois / who_to_query / email-collapse / `is_self` self-relative traversal /
record_reference / merge); `directory/mcp/api.py` thin verb surface; `mcp_server.py` root.
`directory/vocab.py` canonical vocab + write-normalization (folds `Reports-To`→`reports_to`);
`vocab` / `tag` / `find_by_tag` tools; `record_reference` idempotent on (system,value) with
`occurred_at`; tags modeled as kind='tag' entities + 'tagged' edges (no new table); FastMCP
server `instructions` wire look-up-first, follow-through (returned entities/anchors are
the coverage map — query each system before answering) and opportunistic capture. Append-only `interaction` log feeds usage
stats (whois shows `hits`/`last_seen`) and context-aware resolution: `resolve_full` parses
"X from the Y project" and ranks candidates CONNECTION-FIRST (the X actually edged to a
matching Y). Connection is the CONFIDENCE GATE: exactly one plausible candidate → confident
single answer; two or more → `ambiguous: true` and ALL are returned (activity only orders the
best-guess hint, never drops or silently decides — the LLM consumer chooses). `Directory`
takes an injectable `clock`. Name resolution prefers exact/word display-name matches over
notes-only mentions; `relate` is idempotent (dedups on from/to/type). `remember_team` /
`remember_org` create grouping entities (kind team/org) for `member_of`. Anchor writes go
through `_ensure_anchor` (dedup on system+value) so `remember_person`/`link` are idempotent.
~99 tests, ruff + mypy clean. `scripts/graph/build_graph.py` renders the live DB to a
standalone vis-network HTML (`directory-graph.html`), surfaced via the `/directory-graph`
skill (`.claude/skills/`). The script, skill and test ship; only the rendered output is
gitignored (it is a full dump of the directory) so it never lands in the repo.

Registered via `claude mcp add directory` (user scope) and proven live against a real
directory: self + org graph, teams, client orgs, and projects, with `works_on` edges seeded
from GitLab commit authors (`glab` CLI) using alias-email identity collapse. Skill
`directory-enroll` automates the find-across-systems + ask-relationship + record loop.

Distribution (v0.3.0) is plugin-first: `.claude-plugin/plugin.json` bundles the MCP server
(inline `mcpServers` with `${CLAUDE_PLUGIN_ROOT}` — NOT a root `.mcp.json`, which Claude Code
would also read as a broken project-scope server when cwd is this repo), the two skills (moved
`.claude/skills/` → `skills/`, exposed as `directory-mcp:<skill>`), and a SessionStart hook
(`hooks/hooks.json`, matcher startup|resume|clear|compact) that cats `directory-rule.md` into
context — the plugin equivalent of the global-CLAUDE.md rule. `.claude-plugin/marketplace.json`
makes the repo its own marketplace (`claude plugin marketplace add <repo>` then
`claude plugin install directory-mcp@directory-mcp`); toggling is `claude plugin
disable|enable`, `--scope user|project|local`. Structural invariants in
`tests/unit/test_plugin.py`; `claude plugin validate .` passes. The directory-graph skill now
derives the repo root as two-up from its base dir (plugin layout); the manual installer seds
that line to the absolute checkout path instead.

Manual installer (fallback, kept): the proactive-use rule ships as `$CONFIG/directory-rule.md`
plus a single `@./directory-rule.md` import between the existing CLAUDE.md markers (re-running
migrates older inlined installs). Flags: `--uninstall` (skills + rule + block; MCP registration
removal is printed, not run), `--disable` / `--enable` (rename the rule file aside — global
toggle); per-project opt-out via `claudeMdExcludes` is documented in the README. `install.sh`
is covered by `tests/unit/test_install.py`; `install.ps1` mirrors it (no pwsh on this machine
to test).

Landmine: the running MCP server loads code at startup — new tools / resolver changes need a
reconnect to go live in-session, though DB writes are visible immediately.
