"""MCP surface: a thin set of verbs over the directory graph.

The tools read like intentions ("whois", "remember_person", "record_reference"), never
like the schema underneath, so an agent says "check what my boss said" and gets the
person plus the exact coordinates to query the other MCPs — without reasoning about
entities, anchors or edges. All graph shape stays hidden behind this layer.
"""

from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from directory.models import Link
from directory.resolve import Directory, Dossier


def _links(raw: list[dict[str, str]] | None) -> list[Link]:
    return [
        Link(
            system=item["system"],
            ref_type=item["ref_type"],
            value=item["value"],
            label=item.get("label", ""),
        )
        for item in raw or []
    ]


def _entity_dict(entity_id: int, kind: str, name: str) -> dict[str, Any]:
    return {"id": entity_id, "kind": kind, "name": name}


def _iso(at: float | None) -> str | None:
    return datetime.fromtimestamp(at, tz=timezone.utc).isoformat() if at is not None else None


def _dossier_dict(dossier: Dossier) -> dict[str, Any]:
    contacts: dict[str, list[dict[str, str]]] = {}
    for anchor in dossier.anchors:
        contacts.setdefault(anchor.system, []).append(
            {"ref_type": anchor.ref_type, "value": anchor.value, "label": anchor.label}
        )
    return {
        "id": dossier.entity.id,
        "kind": dossier.entity.kind,
        "name": dossier.entity.display_name,
        "notes": dossier.entity.notes,
        "is_self": dossier.entity.is_self,
        "contacts": contacts,
        "relations": [
            {
                "type": r.edge.type,
                "direction": r.direction,
                "name": r.other.display_name,
                "id": r.other.id,
            }
            for r in dossier.relations
        ],
        "observations": [
            {"content": o.content, "key": o.key, "source": o.source} for o in dossier.observations
        ],
        "hits": dossier.stats.count,
        "last_seen": _iso(dossier.stats.last_at),
        "ambiguous": bool(dossier.alternatives),
        "alternatives": [
            _entity_dict(e.id, e.kind, e.display_name) for e in dossier.alternatives
        ],
    }


_INSTRUCTIONS = """\
A consolidation directory of people, projects and artifacts and how to reach them across
whatever systems you use (Slack, Jira, GitLab, GitHub, Outlook, Notion, … — open vocab).
Use it two ways:

LOOK UP — before acting on a person or project, call `whois` (resolves names, emails and
self-relative phrases like "my boss" / "my team") or `who_to_query` to get the exact
coordinates (handle / account id / email) to feed the other MCPs. Don't ask the user who
someone is if the directory knows.

CAPTURE OPPORTUNISTICALLY — the directory only gets smart if you feed it as you work.
Without being asked:
- After reading a thread, ticket, email or meeting, call `record_reference`
  (it is idempotent — safe to call every time) and list the people involved.
- When you learn a person's handle/email/role, call `remember_person`; it collapses on
  shared email so re-recording is safe. Use `links` for any system beyond the named args.
- When you learn an org relationship, call `relate` (e.g. "X" "reports_to" "Y").

STAY CONSISTENT — `kind` / `system` / `ref_type` / relation are open vocab but writes are
normalized. Call `vocab` to see canonical values and what is already in use before
inventing a new one.
"""


def build_mcp_server(*, directory: Directory) -> FastMCP:
    server = FastMCP(name="directory", instructions=_INSTRUCTIONS)

    @server.tool()
    async def whois(query: str) -> dict[str, Any]:
        """Resolve a person/project by name, email, or a self-relative phrase like "my boss".

        Returns who they are, their contacts grouped by system (Slack/Jira/email/…), their
        relationships and recorded facts. This is how you learn where to look for someone.

        When the query is ambiguous (e.g. two similarly-named projects you both work on),
        `ambiguous` is true and `alternatives` lists the other plausible matches — the top
        result is only a best-guess ordering, so YOU should decide between them (ask the user
        or use other context) rather than trusting the first one.
        """
        dossier = await directory.whois(query=query)
        return _dossier_dict(dossier) if dossier else {}

    @server.tool()
    async def who_to_query(query: str) -> dict[str, Any]:
        """The external coordinates for someone, grouped by system — what to feed the other MCPs."""
        entity = await directory.resolve(query=query, touch=True)
        if entity is None:
            return {}
        contacts = await directory.contacts(entity_id=entity.id)
        return {
            system: [{"ref_type": a.ref_type, "value": a.value, "label": a.label} for a in anchors]
            for system, anchors in contacts.items()
        }

    @server.tool()
    async def find(query: str, kind: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Search the directory by name. Optionally narrow by kind (person/project/…)."""
        found = await directory.find(query=query, kind=kind, limit=limit)
        return {"items": [_entity_dict(e.id, e.kind, e.display_name) for e in found]}

    @server.tool()
    async def remember_person(
        name: str,
        email: str | None = None,
        slack_id: str | None = None,
        jira_account_id: str | None = None,
        title: str | None = None,
        links: list[dict[str, str]] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Record a person. Reuses an existing one that shares the email rather than duplicating.

        `slack_id`/`jira_account_id` are shortcuts; `links` attaches any other system as
        `{"system","ref_type","value"}` (e.g. github/notion/linear) so you aren't limited to those.
        """
        person = await directory.remember_person(
            name=name,
            email=email,
            slack_id=slack_id,
            jira_account_id=jira_account_id,
            title=title,
            links=_links(links),
            notes=notes,
        )
        return _entity_dict(person.id, person.kind, person.display_name)

    @server.tool()
    async def remember_project(
        name: str,
        jira_keys: list[str] | None = None,
        slack_channels: list[str] | None = None,
        repos: list[str] | None = None,
        links: list[dict[str, str]] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Record a project with however many Jira keys, Slack channels and repos it spans.

        `links` attaches any other system as `{"system","ref_type","value"}` (e.g. a Notion
        page or GitHub repo) so the project isn't limited to the named keyword coordinates.
        """
        project = await directory.remember_project(
            name=name,
            jira_keys=jira_keys or [],
            slack_channels=slack_channels or [],
            repos=repos or [],
            links=_links(links),
            notes=notes,
        )
        return _entity_dict(project.id, project.kind, project.display_name)

    @server.tool()
    async def remember_team(name: str, notes: str = "") -> dict[str, Any]:
        """Record an internal team/department as an entity, so people can be `member_of` it.

        Find-or-create by name (e.g. "Platform", "QA", "IT", "Support").
        """
        team = await directory.remember_group(kind="team", name=name, notes=notes)
        return _entity_dict(team.id, team.kind, team.display_name)

    @server.tool()
    async def remember_org(name: str, notes: str = "") -> dict[str, Any]:
        """Record an external organization (client/vendor) as an entity for grouping its people.

        Find-or-create by name (e.g. "Globex", "Initech", "Hooli").
        """
        org = await directory.remember_group(kind="org", name=name, notes=notes)
        return _entity_dict(org.id, org.kind, org.display_name)

    @server.tool()
    async def relate(
        subject: str, relation: str, target: str, role: str = "", notes: str = ""
    ) -> dict[str, Any]:
        """Link two entities, e.g. relate("me", "reports_to", "Grace") or ("Ada", "works_on", "Checkout")."""
        edge = await directory.relate(
            subject=subject, relation=relation, target=target, role=role, notes=notes
        )
        return {"linked": edge is not None}

    @server.tool()
    async def link(
        subject: str, system: str, ref_type: str, value: str, label: str = ""
    ) -> dict[str, Any]:
        """Attach an external coordinate (anchor) to an entity — a Slack id, Jira key, repo, URL."""
        anchor = await directory.link(
            subject=subject, system=system, ref_type=ref_type, value=value, label=label
        )
        return {"linked": anchor is not None}

    @server.tool()
    async def note(
        subject: str, fact: str, key: str | None = None, source: str = ""
    ) -> dict[str, Any]:
        """Record a fact about an entity. Set key for a semi-structured attribute (e.g. key='status')."""
        observation = await directory.note(subject=subject, content=fact, key=key, source=source)
        return {"noted": observation is not None}

    @server.tool()
    async def set_self(name: str, email: str | None = None) -> dict[str, Any]:
        """Mark who 'I' am, so self-relative phrases ('my boss', 'my team') resolve."""
        me = await directory.set_self(display_name=name, email=email)
        return _entity_dict(me.id, me.kind, me.display_name)

    @server.tool()
    async def record_reference(
        kind: str,
        system: str,
        ref_type: str,
        value: str,
        title: str,
        url: str = "",
        occurred_at: str = "",
        people: list[str] | None = None,
        role: str = "mentioned",
    ) -> dict[str, Any]:
        """Capture an artifact (slack_thread/ticket/email/meeting) and edge the people on it.

        Idempotent on (system, value) — safe to call every time you read something; unknown
        people are created. `occurred_at` is an ISO timestamp if you have one.
        """
        artifact = await directory.record_reference(
            kind=kind,
            system=system,
            ref_type=ref_type,
            value=value,
            title=title,
            url=url,
            occurred_at=occurred_at,
            people=people or [],
            role=role,
        )
        return _entity_dict(artifact.id, artifact.kind, artifact.display_name)

    @server.tool()
    async def tag(subject: str, label: str) -> dict[str, Any]:
        """Group an entity under a label (e.g. 'leadership', 'checkout-squad') for later filtering."""
        return {"tagged": await directory.tag(subject=subject, label=label)}

    @server.tool()
    async def find_by_tag(label: str) -> dict[str, Any]:
        """List every entity carrying a tag."""
        found = await directory.tagged(label=label)
        return {"items": [_entity_dict(e.id, e.kind, e.display_name) for e in found]}

    @server.tool()
    async def vocab() -> dict[str, Any]:
        """Canonical values for kind/system/ref_type/relation, plus what's already in use.

        Check this before inventing a new value so the directory doesn't fragment.
        """
        return await directory.vocabulary()

    @server.tool()
    async def merge(keep: str, drop: str) -> dict[str, Any]:
        """Fold one entity into another (deduplication), moving all its anchors/edges/facts."""
        return {"merged": await directory.merge(keep=keep, drop=drop)}

    return server
