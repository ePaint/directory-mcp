"""Public surface for the directory store — the one cohesive entity graph.

The directory is a single bounded context, so it is one store, not several: nodes
(`Entity`), their external coordinates (`Anchor`), their relationships (`Edge`) and
sourced facts (`Observation`). Resolution and capture logic live above this layer and
treat it as mechanical persistence. Two implementations share one Protocol — an
in-memory one for tests and a SQLAlchemy one for the real local DB.
"""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import Engine

from directory.models import Anchor, Edge, Entity, InteractionStats, Observation
from directory.persistence import Base
from directory.store.internal.sqlalchemy_store import SqlAlchemyDirectoryStore


class DirectoryStore(Protocol):
    async def add_entity(
        self, *, kind: str, display_name: str, is_self: bool = False, notes: str = ""
    ) -> Entity: ...

    async def get_entity(self, *, entity_id: int) -> Entity | None: ...

    async def self_entity(self) -> Entity | None: ...

    async def find_entities(
        self, *, query: str, kind: str | None = None, limit: int = 20
    ) -> list[Entity]: ...

    async def update_entity(
        self,
        *,
        entity_id: int,
        display_name: str | None = None,
        notes: str | None = None,
        is_self: bool | None = None,
    ) -> Entity: ...

    async def merge_entities(self, *, keep_id: int, drop_id: int) -> None: ...

    async def add_anchor(
        self, *, entity_id: int, system: str, ref_type: str, value: str, label: str = ""
    ) -> Anchor: ...

    async def anchors_for(self, *, entity_id: int, system: str | None = None) -> list[Anchor]: ...

    async def entity_by_anchor(self, *, system: str, value: str) -> Entity | None: ...

    async def add_edge(
        self, *, from_id: int, to_id: int, type: str, role: str = "", notes: str = ""
    ) -> Edge: ...

    async def edges_from(self, *, entity_id: int, type: str | None = None) -> list[Edge]: ...

    async def edges_to(self, *, entity_id: int, type: str | None = None) -> list[Edge]: ...

    async def add_observation(
        self, *, entity_id: int, content: str, key: str | None = None, source: str = ""
    ) -> Observation: ...

    async def observations_for(self, *, entity_id: int) -> list[Observation]: ...

    async def vocabulary(self) -> dict[str, list[str]]: ...

    async def record_interaction(self, *, entity_id: int, kind: str, at: float) -> None: ...

    async def interaction_stats(self, *, entity_id: int) -> InteractionStats: ...


def _search_text(display_name: str, notes: str) -> str:
    return f"{display_name} {notes}".lower()


class InMemoryDirectoryStore:
    def __init__(self) -> None:
        self._entities: dict[int, Entity] = {}
        self._anchors: dict[int, Anchor] = {}
        self._edges: dict[int, Edge] = {}
        self._observations: dict[int, Observation] = {}
        self._interactions: list[tuple[int, float]] = []
        self._next = 0

    def _id(self) -> int:
        self._next += 1
        return self._next

    async def add_entity(
        self, *, kind: str, display_name: str, is_self: bool = False, notes: str = ""
    ) -> Entity:
        entity = Entity(
            id=self._id(), kind=kind, display_name=display_name, is_self=is_self, notes=notes
        )
        self._entities[entity.id] = entity
        return entity

    async def get_entity(self, *, entity_id: int) -> Entity | None:
        return self._entities.get(entity_id)

    async def self_entity(self) -> Entity | None:
        return next((e for e in self._entities.values() if e.is_self), None)

    async def find_entities(
        self, *, query: str, kind: str | None = None, limit: int = 20
    ) -> list[Entity]:
        needle = query.lower()
        matches = [
            e
            for e in self._entities.values()
            if needle in _search_text(e.display_name, e.notes)
            and (kind is None or e.kind == kind)
        ]
        return matches[:limit]

    async def update_entity(
        self,
        *,
        entity_id: int,
        display_name: str | None = None,
        notes: str | None = None,
        is_self: bool | None = None,
    ) -> Entity:
        current = self._entities[entity_id]
        updated = Entity(
            id=current.id,
            kind=current.kind,
            display_name=display_name if display_name is not None else current.display_name,
            is_self=is_self if is_self is not None else current.is_self,
            notes=notes if notes is not None else current.notes,
        )
        self._entities[entity_id] = updated
        return updated

    async def merge_entities(self, *, keep_id: int, drop_id: int) -> None:
        for anchor_id, anchor in list(self._anchors.items()):
            if anchor.entity_id == drop_id:
                self._anchors[anchor_id] = Anchor(
                    id=anchor.id,
                    entity_id=keep_id,
                    system=anchor.system,
                    ref_type=anchor.ref_type,
                    value=anchor.value,
                    label=anchor.label,
                )
        for edge_id, edge in list(self._edges.items()):
            self._edges[edge_id] = Edge(
                id=edge.id,
                from_id=keep_id if edge.from_id == drop_id else edge.from_id,
                to_id=keep_id if edge.to_id == drop_id else edge.to_id,
                type=edge.type,
                role=edge.role,
                notes=edge.notes,
            )
        for obs_id, obs in list(self._observations.items()):
            if obs.entity_id == drop_id:
                self._observations[obs_id] = Observation(
                    id=obs.id,
                    entity_id=keep_id,
                    content=obs.content,
                    key=obs.key,
                    source=obs.source,
                )
        self._entities.pop(drop_id, None)

    async def add_anchor(
        self, *, entity_id: int, system: str, ref_type: str, value: str, label: str = ""
    ) -> Anchor:
        anchor = Anchor(
            id=self._id(),
            entity_id=entity_id,
            system=system,
            ref_type=ref_type,
            value=value,
            label=label,
        )
        self._anchors[anchor.id] = anchor
        return anchor

    async def anchors_for(self, *, entity_id: int, system: str | None = None) -> list[Anchor]:
        return [
            a
            for a in self._anchors.values()
            if a.entity_id == entity_id and (system is None or a.system == system)
        ]

    async def entity_by_anchor(self, *, system: str, value: str) -> Entity | None:
        anchor = next(
            (
                a
                for a in self._anchors.values()
                if a.system == system and a.value.lower() == value.lower()
            ),
            None,
        )
        return self._entities.get(anchor.entity_id) if anchor else None

    async def add_edge(
        self, *, from_id: int, to_id: int, type: str, role: str = "", notes: str = ""
    ) -> Edge:
        edge = Edge(id=self._id(), from_id=from_id, to_id=to_id, type=type, role=role, notes=notes)
        self._edges[edge.id] = edge
        return edge

    async def edges_from(self, *, entity_id: int, type: str | None = None) -> list[Edge]:
        return [
            e
            for e in self._edges.values()
            if e.from_id == entity_id and (type is None or e.type == type)
        ]

    async def edges_to(self, *, entity_id: int, type: str | None = None) -> list[Edge]:
        return [
            e
            for e in self._edges.values()
            if e.to_id == entity_id and (type is None or e.type == type)
        ]

    async def add_observation(
        self, *, entity_id: int, content: str, key: str | None = None, source: str = ""
    ) -> Observation:
        obs = Observation(
            id=self._id(), entity_id=entity_id, content=content, key=key, source=source
        )
        self._observations[obs.id] = obs
        return obs

    async def observations_for(self, *, entity_id: int) -> list[Observation]:
        return [o for o in self._observations.values() if o.entity_id == entity_id]

    async def vocabulary(self) -> dict[str, list[str]]:
        return {
            "kind": sorted({e.kind for e in self._entities.values()}),
            "system": sorted({a.system for a in self._anchors.values()}),
            "ref_type": sorted({a.ref_type for a in self._anchors.values()}),
            "relation": sorted({e.type for e in self._edges.values()}),
        }

    async def record_interaction(self, *, entity_id: int, kind: str, at: float) -> None:
        self._interactions.append((entity_id, at))

    async def interaction_stats(self, *, entity_id: int) -> InteractionStats:
        ats = [at for eid, at in self._interactions if eid == entity_id]
        return InteractionStats(count=len(ats), last_at=max(ats) if ats else None)


def build_directory_store(*, engine: Engine) -> DirectoryStore:
    Base.metadata.create_all(engine)
    return SqlAlchemyDirectoryStore(engine=engine)


__all__: Sequence[str] = ["DirectoryStore", "InMemoryDirectoryStore", "build_directory_store"]
