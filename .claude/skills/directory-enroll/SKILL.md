---
name: directory-enroll
description: Find people across whatever people-search MCPs you have (Slack / Jira / GitHub / Outlook / …) and record them in the local `directory` MCP, asking the user their relationship to each. Use when the user wants to add a person or a set of people to the directory — e.g. "add Alex", "enroll everyone in my meetings this month", "build out my org graph", "find and add the people from <source>" — or invokes `/directory-enroll`. Resolves each person's cross-platform identities, collapses them by email, and records a relationship edge to the user.
---

# directory-enroll

Turn a name (or a source-of-people) into `directory` entries carrying every cross-platform
anchor, plus a relationship edge to the connected user. Discovery is automatic; the
relationship is the ONE thing only the user knows — so ask it, don't guess.

## Preconditions

- The `directory` MCP must be connected (tools `whois`, `remember_person`, `relate`,
  `set_self`, `who_to_query`, `vocab`, `tag`).
- **Ensure "me" is set once.** Call `whois "me"`. If it returns `{}`, call `set_self` with the
  connected user's name + email before recording any relationships — self-relative edges
  depend on it.
- **Know which people-search MCPs are connected.** Discovery uses whatever you have — a chat
  MCP (Slack/Teams/…), an issue-tracker MCP (Jira/GitHub/Linear/…), a mail/calendar MCP
  (Outlook/Google/…). None are required; use the ones present and note the gaps. If a system
  needs a one-time handle (e.g. an Atlassian cloudId), fetch it once and reuse it.

## Per-person process

1. **Skip if already known.** `whois "<name or email>"`. If it resolves confidently with the
   anchors already present, skip — the directory is idempotent, don't re-ask.
2. **Resolve across systems (read only — do NOT write yet):** query each connected
   people-search MCP for the person's coordinate in that system — a chat user id, an
   issue-tracker account id, a repo handle, an email. Examples by system:
   - Chat (Slack/Teams): search users by name → user id, email, real name.
   - Issue tracker (Jira/GitHub/Linear): look up an account/login by email (fall back to name).
   - Mail/calendar: the email is often already known from the source; otherwise search.
   - **Collapse on shared email** — same address ⇒ same person. If the name matches several
     distinct people, list them and ask the user which one (or enroll all, clearly labelled).
3. **Ask the relationship** with AskUserQuestion. Batch up to 4 people per call (one question
   each). Standard options — keep labels short:
   - **Boss** (they manage me) · **My report** (I manage them) · **Peer** (same level) ·
     **Collaborator** (work together, no reporting line)
   - The user can always pick "Other" and type a free-text relation.
   - Skip the question for anyone whose relationship the user already stated in the conversation.
4. **Record:**
   - `remember_person name=… email=… slack_id=… jira_account_id=… title=…` (collapses on email,
     safe to repeat). For any system without a named argument (GitHub, Notion, Linear, …) pass
     `links=[{"system","ref_type","value"}]`.
   - `relate` per the mapping below, using `"me"` as the self anchor.
   - Optional: `tag` the person (e.g. a team or project) if the source implies it.
5. **Report** what was written (name → anchors + edge), and flag anyone not found in a system.

## Relationship → edge mapping

| Answer | Edge |
|---|---|
| Boss / manager | `relate subject="me" relation="reports_to" target="<them>"` |
| My report | `relate subject="<them>" relation="reports_to" target="me"` |
| Peer | `relate subject="me" relation="peer" target="<them>"` |
| Collaborator | `relate subject="me" relation="collaborates_with" target="<them>"` |
| Other (free text) | normalize the user's word against `vocab`, then `relate` with it |

## Bulk source: meetings / threads

When the source is "people from my meetings this/past <period>" (or a chat channel, a thread,
an email chain):
- Pull the roster from the relevant MCP (e.g. a calendar search over the window → attendees;
  a channel's members; a thread's participants) → collect `name`, `email`.
- **Dedupe by email.** Drop the user themselves, meeting rooms, and distribution lists.
- Decide on external addresses: by default enroll only your org's email domain; ask before
  adding outside contacts.
- Show the deduped roster first, THEN run the per-person process and batch the relationship
  questions so the user answers a few at a time.

## Guardrails

- Never fabricate an identity. No match in a system ⇒ record what you have and note the gap.
- Check `vocab` before inventing a new relation/system value.
- Idempotent by design: re-running re-resolves and `whois`-skips; email collapse prevents dupes.
- Only the relationship comes from the user; everything else is discovered.
