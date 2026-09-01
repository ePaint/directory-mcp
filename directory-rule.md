## directory MCP — use it proactively

**Always use the `directory` MCP, proactively, in every session — without being asked.**
Whenever a person, project, team or org is referenced — including self-relative phrases like
"my boss" / "my team" — look it up FIRST with `whois` (who they are + their relationships) or
`who_to_query` (the exact coordinates to feed the other MCPs). Never ask who someone is if the
directory can answer. Follow through on what it returns: the entities and anchors that come
back (email / slack_thread / ticket / channel / repo / …) are the coverage map for that
subject — each names a system to actually query before answering; don't cherry-pick the
familiar ones. Capture opportunistically too: as you learn a handle / email / role, an
org relationship, or touch an artifact (thread, ticket, email, meeting), record it without
being asked — `remember_person` (collapses on shared email), `relate`, `record_reference`
(idempotent). Check `vocab` before inventing a new `kind` / `system` / `ref_type` / relation
value. When spawning sub-agents for work involving people or projects, pass this rule along.
If the `directory` MCP is not connected in a session, skip silently — never block on it.
