"""Canonical vocabulary and write-normalization for the open-vocab fields.

`kind` / `system` / `ref_type` / relation `type` stay free strings so a new system never
needs a migration — but free strings drift (`reports-to` vs `reports_to` vs `manages`),
and a directory whose whole job is consolidation must not fragment itself. So writes are
normalized toward a canonical form here, and the `vocab` tool surfaces these suggestions
plus what is actually in use. Unknown values are slugged and kept, never rejected.
"""

_FACETS: dict[str, dict[str, list[str]]] = {
    "kind": {
        "person": ["people", "human", "user", "contact", "individual"],
        "project": ["initiative", "workstream", "epic"],
        "team": ["squad", "group", "guild"],
        "org": ["organization", "organisation", "company", "department", "division"],
        "slack_thread": ["thread", "conversation"],
        "ticket": ["issue", "jira_issue", "bug", "story"],
        "email": ["mail", "message"],
        "meeting": ["event", "call", "sync"],
        "doc": ["document", "page", "transcript", "spec"],
        "resource": ["asset", "tool"],
        "artifact": [],
        "tag": [],
    },
    "system": {
        "slack": [],
        "jira": [],
        "gitlab": ["git", "gitlab.com"],
        "github": ["gh"],
        "outlook": ["o365", "office365", "exchange", "ms365"],
        "email": ["mail", "e_mail"],
        "confluence": ["wiki"],
        "sharepoint": ["onedrive", "pianodrive"],
        "url": ["link", "web", "http"],
        "tag": [],
    },
    "ref_type": {
        "user": ["member", "person", "account", "account_id"],
        "channel": ["chan"],
        "project_key": ["project", "jira_project", "key"],
        "repo": ["repository"],
        "issue": ["ticket", "issue_key"],
        "epic": [],
        "address": [],
        "thread": ["message_ts", "ts"],
        "message": ["msg"],
        "page": [],
        "deck": ["slides", "presentation"],
        "label": [],
        "url": ["link"],
    },
    "relation": {
        "reports_to": ["reports", "reportsto"],
        "manages": ["manage", "manager_of"],
        "member_of": ["member", "belongs_to"],
        "part_of": ["subproject_of", "child_of"],
        "peer": ["peers", "peer_of", "colleague"],
        "works_on": ["working_on", "works"],
        "collaborates_with": ["collaborates", "works_with", "collaborator"],
        "stakeholder_of": ["stakeholder", "attends", "attendee"],
        "sponsors": ["sponsor", "sponsored_by"],
        "leads": ["lead", "leading", "owns", "owner_of"],
        "authored": ["author", "wrote", "created"],
        "mentions": ["mentioned", "mention"],
        "assigned": ["assignee", "assigned_to"],
        "tagged": ["tag"],
        "relates_to": ["related", "relates", "related_to"],
    },
}


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _reverse(facet: str) -> dict[str, str]:
    mapping = {_slug(canonical): canonical for canonical in _FACETS[facet]}
    for canonical, aliases in _FACETS[facet].items():
        for alias in aliases:
            mapping[_slug(alias)] = canonical
    return mapping


_REVERSE: dict[str, dict[str, str]] = {facet: _reverse(facet) for facet in _FACETS}


def normalize(facet: str, value: str) -> str:
    """Fold a value toward its canonical form; unknown values are kept (just slugged)."""
    slug = _slug(value)
    return _REVERSE.get(facet, {}).get(slug, slug)


def normalize_kind(value: str) -> str:
    return normalize("kind", value)


def normalize_system(value: str) -> str:
    return normalize("system", value)


def normalize_ref_type(value: str) -> str:
    return normalize("ref_type", value)


def normalize_relation(value: str) -> str:
    return normalize("relation", value)


def normalize_key(value: str) -> str:
    return _slug(value)


def suggested() -> dict[str, list[str]]:
    return {facet: sorted(values) for facet, values in _FACETS.items()}
