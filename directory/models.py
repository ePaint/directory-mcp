"""Domain models for the directory graph.

The whole directory is four node/edge shapes, deliberately untyped beyond a `kind`
string, so a messy org (a project with many Jira keys, scattered Slack channels,
several repos, sub-projects) is expressed as more rows, never a schema change.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    """A node: a person, project, team, org, artifact — `kind` is open vocab."""

    id: int
    kind: str
    display_name: str
    is_self: bool = False
    notes: str = ""


@dataclass(frozen=True)
class Anchor:
    """An external coordinate of an entity. Many per entity; this is the resolver.

    `system` is where it lives (slack/jira/gitlab/outlook/email/url), `ref_type` is what
    it is there (user/channel/project_key/repo/issue/address), `value` is the coordinate.
    """

    id: int
    entity_id: int
    system: str
    ref_type: str
    value: str
    label: str = ""


@dataclass(frozen=True)
class Link:
    """A coordinate to attach to an entity, before it is stored as an `Anchor`.

    The uniform way `remember_person`/`remember_project` take coordinates — every system
    (slack, jira, github, notion, …) goes through `links`, none is privileged, so the surface
    isn't fixed to one org's MCP set.
    """

    system: str
    ref_type: str
    value: str
    label: str = ""


@dataclass(frozen=True)
class Edge:
    """A directed, free-text-typed relationship between two entities.

    Org graph, project membership, sub-projects and artifact references are all edges.
    """

    id: int
    from_id: int
    to_id: int
    type: str
    role: str = ""
    notes: str = ""


@dataclass(frozen=True)
class Observation:
    """An atomic, sourced fact about an entity. `key` set makes it a semi-structured attribute."""

    id: int
    entity_id: int
    content: str
    key: str | None = None
    source: str = ""


@dataclass(frozen=True)
class InteractionStats:
    """Usage signal derived from the append-only interaction log: how often, how recently."""

    count: int
    last_at: float | None
