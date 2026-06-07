"""The Directory facade — policy and convenience over the mechanical store.

This is where the messy-org intent lives: collapse identities by email, resolve a
self-relative phrase ("my boss") to a real entity by walking edges from `is_self`, and
capture a reference (artifact + the people on it) in one call. The store below stays
dumb; the judgement calls (auto-collapse vs. manual merge, phrase → traversal) live here.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from directory import vocab
from directory.models import Anchor, Edge, Entity, InteractionStats, Link, Observation
from directory.store.api import DirectoryStore

_CONTEXT_NOISE = {"project", "projects", "team", "squad", "initiative", "the", "work", "effort"}
_CONTEXT_SEPARATORS = (" from the ", " from ", " on the ", " on ", " in the ", " in ")

_SELF_WORDS = {"me", "myself", "i", "my self"}

_SELF_RELATIVE: dict[str, tuple[str, str]] = {
    "boss": ("reports_to", "out"),
    "manager": ("reports_to", "out"),
    "report": ("reports_to", "in"),
    "reports": ("reports_to", "in"),
    "directs": ("reports_to", "in"),
    "team": ("member_of", "out"),
    "peer": ("peer", "out"),
    "peers": ("peer", "out"),
}


@dataclass(frozen=True)
class Relation:
    edge: Edge
    other: Entity
    direction: str


_ACTIVITY_HALF_LIFE_SECONDS = 14 * 24 * 3600


@dataclass(frozen=True)
class Dossier:
    entity: Entity
    anchors: list[Anchor]
    relations: list[Relation]
    observations: list[Observation]
    stats: InteractionStats
    alternatives: list[Entity]


@dataclass(frozen=True)
class _Scored:
    entity: Entity
    name_score: int
    connected: bool
    context_score: float
    own_score: float
    context: Entity | None

    @property
    def rank(self) -> tuple[bool, int, float, float]:
        return (self.connected, self.name_score, self.context_score, self.own_score)


def _name_score(display_name: str, query: str) -> int:
    name = display_name.strip().lower()
    needle = query.strip().lower()
    if name == needle:
        return 3
    if name.startswith(needle) or needle in name.split():
        return 2
    if needle in name:
        return 1
    return 0


@dataclass(frozen=True)
class Resolution:
    entity: Entity | None
    alternatives: list[Entity]
    context: Entity | None


def _self_relative(query: str) -> tuple[str, str] | None:
    token = query.strip().lower().removeprefix("my ").strip()
    return _SELF_RELATIVE.get(token)


def _split_context(query: str) -> tuple[str, str | None]:
    """Split "alex from the acme project" into ("alex", "acme project")."""
    lowered = query.lower()
    for separator in _CONTEXT_SEPARATORS:
        index = lowered.find(separator)
        if index != -1:
            subject = query[:index].strip()
            context = query[index + len(separator) :].strip()
            if subject and context:
                return subject, context
    return query.strip(), None


def _context_core(hint: str) -> str:
    words = [w for w in hint.lower().split() if w not in _CONTEXT_NOISE]
    return " ".join(words) if words else hint.strip()


class Directory:
    def __init__(
        self, *, store: DirectoryStore, clock: Callable[[], float] = time.time
    ) -> None:
        self.store = store
        self._clock = clock

    async def find(self, *, query: str, kind: str | None = None, limit: int = 20) -> list[Entity]:
        return await self.store.find_entities(query=query, kind=kind, limit=limit)

    async def resolve(self, *, query: str, touch: bool = False) -> Entity | None:
        return (await self.resolve_full(query=query, touch=touch)).entity

    async def resolve_full(self, *, query: str, touch: bool = False) -> Resolution:
        """Resolve a name, email, or self-relative/contextual phrase, keeping the runners-up.

        Handles "my boss" (self-relative), "ada@example.com" (email), and "alex from the acme
        project". For the contextual case, CONNECTION is the primary signal — the subject who
        is actually linked to a matching context wins — and the context's activity (how often
        and how recently it is touched) only breaks ties between several connected candidates,
        so a small recency gap can't flip the result on its own. `alternatives` carries the
        plausible runners-up so an ambiguous match is visible, not silently guessed.
        """
        if query.strip().lower() in _SELF_WORDS:
            me = await self.store.self_entity()
            await self._reinforce(me, None, touch)
            return Resolution(entity=me, alternatives=[], context=None)

        relative = _self_relative(query)
        if relative is not None:
            neighbours = await self._self_neighbours(*relative)
            entity = neighbours[0] if neighbours else None
            await self._reinforce(entity, None, touch)
            return Resolution(entity=entity, alternatives=neighbours[1:], context=None)

        subject, context = _split_context(query)
        if context is not None:
            resolution = await self._resolve_in_context(subject, context)
            if resolution.entity is not None:
                await self._reinforce(resolution.entity, resolution.context, touch)
                return resolution

        if "@" in subject:
            by_email = await self.store.entity_by_anchor(system="email", value=subject)
            if by_email is not None:
                await self._reinforce(by_email, None, touch)
                return Resolution(entity=by_email, alternatives=[], context=None)

        return await self._resolve_named(subject, touch)

    async def _resolve_named(self, name: str, touch: bool) -> Resolution:
        candidates = await self.store.find_entities(query=name, limit=25)
        ranked = await self._ranked(candidates, match=name)
        if not ranked:
            return Resolution(entity=None, alternatives=[], context=None)
        winner = ranked[0]
        await self._reinforce(winner.entity, None, touch)
        return Resolution(
            entity=winner.entity, alternatives=self._alternatives(ranked), context=None
        )

    async def _resolve_in_context(self, subject: str, context: str) -> Resolution:
        contexts = await self.store.find_entities(query=_context_core(context), limit=25)
        context_ids = {c.id for c in contexts}
        candidates = [
            c
            for c in await self.store.find_entities(query=subject, limit=25)
            if c.id not in context_ids
        ]
        if not candidates:
            return Resolution(entity=None, alternatives=[], context=None)
        ranked = await self._ranked(candidates, match=subject, contexts=contexts)
        winner = ranked[0]
        return Resolution(
            entity=winner.entity,
            alternatives=self._alternatives(ranked),
            context=winner.context,
        )

    async def _ranked(
        self, candidates: Sequence[Entity], *, match: str, contexts: Sequence[Entity] = ()
    ) -> list[_Scored]:
        now = self._clock()
        scored: list[_Scored] = []
        for candidate in candidates:
            context, context_score = await self._best_connected_context(candidate.id, contexts, now)
            scored.append(
                _Scored(
                    entity=candidate,
                    name_score=_name_score(candidate.display_name, match),
                    connected=context is not None,
                    context_score=context_score,
                    own_score=await self._activity(candidate.id, now),
                    context=context,
                )
            )
        scored.sort(key=lambda s: s.rank, reverse=True)
        return scored

    def _alternatives(self, ranked: Sequence[_Scored]) -> list[Entity]:
        winner = ranked[0]
        return [
            other.entity
            for other in ranked[1:6]
            if other.entity.kind == winner.entity.kind
            and other.connected == winner.connected
            and other.name_score == winner.name_score
        ]

    async def _best_connected_context(
        self, entity_id: int, contexts: Sequence[Entity], now: float
    ) -> tuple[Entity | None, float]:
        best: Entity | None = None
        best_score = 0.0
        for context in contexts:
            if not await self._connected(entity_id, context.id):
                continue
            score = await self._activity(context.id, now)
            if best is None or score > best_score:
                best, best_score = context, score
        return best, best_score

    async def _activity(self, entity_id: int, now: float) -> float:
        """Frequency × recency-decay — high for the thing being actively worked right now."""
        stats = await self.store.interaction_stats(entity_id=entity_id)
        if stats.last_at is None:
            return 0.0
        decay: float = 0.5 ** ((now - stats.last_at) / _ACTIVITY_HALF_LIFE_SECONDS)
        return stats.count * decay

    async def _connected(self, a_id: int, b_id: int) -> bool:
        outgoing = await self.store.edges_from(entity_id=a_id)
        if any(e.to_id == b_id for e in outgoing):
            return True
        incoming = await self.store.edges_to(entity_id=a_id)
        return any(e.from_id == b_id for e in incoming)

    async def _touch(self, entity_id: int, kind: str) -> None:
        await self.store.record_interaction(entity_id=entity_id, kind=kind, at=self._clock())

    async def _reinforce(self, entity: Entity | None, context: Entity | None, touch: bool) -> None:
        if not touch:
            return
        if entity is not None:
            await self._touch(entity.id, "lookup")
        if context is not None:
            await self._touch(context.id, "lookup")

    async def _self_neighbours(self, edge_type: str, direction: str) -> list[Entity]:
        me = await self.store.self_entity()
        if me is None:
            return []
        if direction == "out":
            edges = await self.store.edges_from(entity_id=me.id, type=edge_type)
            other_ids = [e.to_id for e in edges]
        else:
            edges = await self.store.edges_to(entity_id=me.id, type=edge_type)
            other_ids = [e.from_id for e in edges]
        neighbours = [await self.store.get_entity(entity_id=other_id) for other_id in other_ids]
        return [n for n in neighbours if n is not None]

    async def dossier(
        self, *, entity_id: int, alternatives: Sequence[Entity] = ()
    ) -> Dossier | None:
        entity = await self.store.get_entity(entity_id=entity_id)
        if entity is None:
            return None
        anchors = await self.store.anchors_for(entity_id=entity_id)
        observations = await self.store.observations_for(entity_id=entity_id)
        relations = await self._relations(entity_id)
        stats = await self.store.interaction_stats(entity_id=entity_id)
        return Dossier(
            entity=entity,
            anchors=anchors,
            relations=relations,
            observations=observations,
            stats=stats,
            alternatives=list(alternatives),
        )

    async def whois(self, *, query: str) -> Dossier | None:
        resolution = await self.resolve_full(query=query, touch=True)
        if resolution.entity is None:
            return None
        return await self.dossier(
            entity_id=resolution.entity.id, alternatives=resolution.alternatives
        )

    async def contacts(self, *, entity_id: int) -> dict[str, list[Anchor]]:
        """External coordinates grouped by system — what to feed the other MCPs."""
        grouped: dict[str, list[Anchor]] = {}
        for anchor in await self.store.anchors_for(entity_id=entity_id):
            grouped.setdefault(anchor.system, []).append(anchor)
        return grouped

    async def _relations(self, entity_id: int) -> list[Relation]:
        relations: list[Relation] = []
        for edge in await self.store.edges_from(entity_id=entity_id):
            other = await self.store.get_entity(entity_id=edge.to_id)
            if other is not None:
                relations.append(Relation(edge=edge, other=other, direction="out"))
        for edge in await self.store.edges_to(entity_id=entity_id):
            other = await self.store.get_entity(entity_id=edge.from_id)
            if other is not None:
                relations.append(Relation(edge=edge, other=other, direction="in"))
        return relations

    async def ensure_person(
        self, *, display_name: str, email: str | None = None, notes: str = ""
    ) -> Entity:
        """Find-or-create a person, collapsing onto an existing one that shares the email."""
        if email is not None:
            existing = await self.store.entity_by_anchor(system="email", value=email)
            if existing is not None:
                return existing
        person = await self.store.add_entity(
            kind="person", display_name=display_name, notes=notes
        )
        if email is not None:
            await self._ensure_anchor(
                entity_id=person.id, system="email", ref_type="address", value=email
            )
        return person

    async def remember_person(
        self,
        *,
        name: str,
        email: str | None = None,
        title: str | None = None,
        links: Sequence[Link] = (),
        notes: str = "",
    ) -> Entity:
        person = await self.ensure_person(display_name=name, email=email, notes=notes)
        await self._apply_links(entity_id=person.id, links=links)
        if title is not None:
            await self.store.add_observation(
                entity_id=person.id, content=title, key="title", source="manual"
            )
        return person

    async def set_self(self, *, display_name: str, email: str | None = None) -> Entity:
        person = await self.ensure_person(display_name=display_name, email=email)
        return await self.store.update_entity(entity_id=person.id, is_self=True)

    async def relate(
        self, *, subject: str, relation: str, target: str, role: str = "", notes: str = ""
    ) -> Edge | None:
        subject_entity = await self.resolve(query=subject)
        target_entity = await self.resolve(query=target)
        if subject_entity is None or target_entity is None:
            return None
        relation_type = vocab.normalize_relation(relation)
        for edge in await self.store.edges_from(entity_id=subject_entity.id, type=relation_type):
            if edge.to_id == target_entity.id:
                return edge
        return await self.store.add_edge(
            from_id=subject_entity.id,
            to_id=target_entity.id,
            type=relation_type,
            role=role,
            notes=notes,
        )

    async def link(
        self, *, subject: str, system: str, ref_type: str, value: str, label: str = ""
    ) -> Anchor | None:
        entity = await self.resolve(query=subject)
        if entity is None:
            return None
        return await self._ensure_anchor(
            entity_id=entity.id,
            system=vocab.normalize_system(system),
            ref_type=vocab.normalize_ref_type(ref_type),
            value=value,
            label=label,
        )

    async def note(
        self, *, subject: str, content: str, key: str | None = None, source: str = ""
    ) -> Observation | None:
        entity = await self.resolve(query=subject)
        if entity is None:
            return None
        return await self.store.add_observation(
            entity_id=entity.id,
            content=content,
            key=vocab.normalize_key(key) if key is not None else None,
            source=source,
        )

    async def remember_group(self, *, kind: str, name: str, notes: str = "") -> Entity:
        """Find-or-create a non-person grouping entity (team / org / department) by name.

        Groups have no email to collapse on, so dedup is an exact (kind, name) match.
        """
        normalized = vocab.normalize_kind(kind)
        for candidate in await self.store.find_entities(query=name, kind=normalized, limit=25):
            if candidate.display_name.lower() == name.lower():
                return candidate
        return await self.store.add_entity(kind=normalized, display_name=name, notes=notes)

    async def remember_project(
        self,
        *,
        name: str,
        links: Sequence[Link] = (),
        notes: str = "",
    ) -> Entity:
        """A project with however many coordinates (Jira keys, channels, repos, …) it sprawls across."""
        project = await self.store.add_entity(kind="project", display_name=name, notes=notes)
        await self._apply_links(entity_id=project.id, links=links)
        return project

    async def _apply_links(self, *, entity_id: int, links: Sequence[Link]) -> None:
        for link in links:
            await self._ensure_anchor(
                entity_id=entity_id,
                system=vocab.normalize_system(link.system),
                ref_type=vocab.normalize_ref_type(link.ref_type),
                value=link.value,
                label=link.label,
            )

    async def record_reference(
        self,
        *,
        kind: str,
        system: str,
        ref_type: str,
        value: str,
        title: str,
        url: str = "",
        occurred_at: str = "",
        people: Sequence[str] = (),
        role: str = "mentioned",
    ) -> Entity:
        """Capture an artifact (thread/ticket/email/meeting) and edge the people on it to it.

        Idempotent: re-recording the same coordinate reuses the artifact instead of duplicating,
        so calling this opportunistically every time you read something is safe.
        """
        system = vocab.normalize_system(system)
        ref_type = vocab.normalize_ref_type(ref_type)
        role = vocab.normalize_relation(role)
        artifact = await self.store.entity_by_anchor(system=system, value=value)
        if artifact is None:
            artifact = await self.store.add_entity(
                kind=vocab.normalize_kind(kind), display_name=title, notes=url
            )
            await self._ensure_anchor(
                entity_id=artifact.id, system=system, ref_type=ref_type, value=value, label=title
            )
        if occurred_at:
            await self._set_attribute(artifact.id, "occurred_at", occurred_at, source=system)
        await self._touch(artifact.id, "reference")
        for who in people:
            person = await self.resolve(query=who)
            if person is None:
                person = await self.ensure_person(display_name=who)
            await self._ensure_edge(from_id=person.id, to_id=artifact.id, type=role)
            await self._touch(person.id, "reference")
        return artifact

    async def tag(self, *, subject: str, label: str) -> bool:
        """Tag an entity. A tag is a kind='tag' entity; tagging is a 'tagged' edge — no new schema."""
        entity = await self.resolve(query=subject)
        if entity is None:
            return False
        tag_entity = await self._ensure_tag(label)
        await self._ensure_edge(from_id=entity.id, to_id=tag_entity.id, type="tagged")
        return True

    async def tagged(self, *, label: str) -> list[Entity]:
        tag_entity = await self.store.entity_by_anchor(system="tag", value=vocab.normalize_key(label))
        if tag_entity is None:
            return []
        edges = await self.store.edges_to(entity_id=tag_entity.id, type="tagged")
        tagged: list[Entity] = []
        for edge in edges:
            entity = await self.store.get_entity(entity_id=edge.from_id)
            if entity is not None:
                tagged.append(entity)
        return tagged

    async def vocabulary(self) -> dict[str, dict[str, list[str]]]:
        """What values to use: canonical suggestions plus what is already in this directory."""
        return {"suggested": vocab.suggested(), "in_use": await self.store.vocabulary()}

    async def _ensure_tag(self, label: str) -> Entity:
        slug = vocab.normalize_key(label)
        existing = await self.store.entity_by_anchor(system="tag", value=slug)
        if existing is not None:
            return existing
        tag_entity = await self.store.add_entity(kind="tag", display_name=label)
        await self._ensure_anchor(
            entity_id=tag_entity.id, system="tag", ref_type="label", value=slug
        )
        return tag_entity

    async def _ensure_edge(self, *, from_id: int, to_id: int, type: str) -> None:
        existing = await self.store.edges_from(entity_id=from_id, type=type)
        if any(e.to_id == to_id for e in existing):
            return
        await self.store.add_edge(from_id=from_id, to_id=to_id, type=type)

    async def _ensure_anchor(
        self, *, entity_id: int, system: str, ref_type: str, value: str, label: str = ""
    ) -> Anchor:
        for anchor in await self.store.anchors_for(entity_id=entity_id, system=system):
            if anchor.value.lower() == value.lower():
                return anchor
        return await self.store.add_anchor(
            entity_id=entity_id, system=system, ref_type=ref_type, value=value, label=label
        )

    async def _set_attribute(self, entity_id: int, key: str, value: str, *, source: str) -> None:
        for obs in await self.store.observations_for(entity_id=entity_id):
            if obs.key == key:
                return
        await self.store.add_observation(
            entity_id=entity_id, content=value, key=key, source=source
        )

    async def merge(self, *, keep: str, drop: str) -> bool:
        keep_entity = await self.resolve(query=keep)
        drop_entity = await self.resolve(query=drop)
        if keep_entity is None or drop_entity is None or keep_entity.id == drop_entity.id:
            return False
        await self.store.merge_entities(keep_id=keep_entity.id, drop_id=drop_entity.id)
        return True
