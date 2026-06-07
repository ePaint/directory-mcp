"""SQLAlchemy-backed directory store. Sync SQLAlchemy runs in a worker thread.

Mirrors slack-mcp's directory cache: name search is a `search_text` column queried with
LIKE (no FTS), anchor resolution is a case-insensitive equality on (system, value).
"""

import asyncio

from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.orm import Session

from directory.models import Anchor, Edge, Entity, InteractionStats, Observation
from directory.store.internal.tables import (
    AnchorRow,
    EdgeRow,
    EntityRow,
    InteractionRow,
    ObservationRow,
)


def _search_text(display_name: str, notes: str) -> str:
    return f"{display_name} {notes}".lower()


class SqlAlchemyDirectoryStore:
    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    async def add_entity(
        self, *, kind: str, display_name: str, is_self: bool = False, notes: str = ""
    ) -> Entity:
        return await asyncio.to_thread(self._add_entity, kind, display_name, is_self, notes)

    async def get_entity(self, *, entity_id: int) -> Entity | None:
        return await asyncio.to_thread(self._get_entity, entity_id)

    async def self_entity(self) -> Entity | None:
        return await asyncio.to_thread(self._self_entity)

    async def find_entities(
        self, *, query: str, kind: str | None = None, limit: int = 20
    ) -> list[Entity]:
        return await asyncio.to_thread(self._find_entities, query, kind, limit)

    async def update_entity(
        self,
        *,
        entity_id: int,
        display_name: str | None = None,
        notes: str | None = None,
        is_self: bool | None = None,
    ) -> Entity:
        return await asyncio.to_thread(
            self._update_entity, entity_id, display_name, notes, is_self
        )

    async def merge_entities(self, *, keep_id: int, drop_id: int) -> None:
        await asyncio.to_thread(self._merge_entities, keep_id, drop_id)

    async def add_anchor(
        self, *, entity_id: int, system: str, ref_type: str, value: str, label: str = ""
    ) -> Anchor:
        return await asyncio.to_thread(self._add_anchor, entity_id, system, ref_type, value, label)

    async def anchors_for(self, *, entity_id: int, system: str | None = None) -> list[Anchor]:
        return await asyncio.to_thread(self._anchors_for, entity_id, system)

    async def entity_by_anchor(self, *, system: str, value: str) -> Entity | None:
        return await asyncio.to_thread(self._entity_by_anchor, system, value)

    async def add_edge(
        self, *, from_id: int, to_id: int, type: str, role: str = "", notes: str = ""
    ) -> Edge:
        return await asyncio.to_thread(self._add_edge, from_id, to_id, type, role, notes)

    async def edges_from(self, *, entity_id: int, type: str | None = None) -> list[Edge]:
        return await asyncio.to_thread(self._edges_from, entity_id, type)

    async def edges_to(self, *, entity_id: int, type: str | None = None) -> list[Edge]:
        return await asyncio.to_thread(self._edges_to, entity_id, type)

    async def add_observation(
        self, *, entity_id: int, content: str, key: str | None = None, source: str = ""
    ) -> Observation:
        return await asyncio.to_thread(self._add_observation, entity_id, content, key, source)

    async def observations_for(self, *, entity_id: int) -> list[Observation]:
        return await asyncio.to_thread(self._observations_for, entity_id)

    async def vocabulary(self) -> dict[str, list[str]]:
        return await asyncio.to_thread(self._vocabulary)

    async def record_interaction(self, *, entity_id: int, kind: str, at: float) -> None:
        await asyncio.to_thread(self._record_interaction, entity_id, kind, at)

    async def interaction_stats(self, *, entity_id: int) -> InteractionStats:
        return await asyncio.to_thread(self._interaction_stats, entity_id)

    def _add_entity(self, kind: str, display_name: str, is_self: bool, notes: str) -> Entity:
        row = EntityRow(
            kind=kind,
            display_name=display_name,
            search_text=_search_text(display_name, notes),
            is_self=is_self,
            notes=notes,
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_entity(row)

    def _get_entity(self, entity_id: int) -> Entity | None:
        with Session(self._engine) as session:
            row = session.get(EntityRow, entity_id)
            return _to_entity(row) if row else None

    def _self_entity(self) -> Entity | None:
        with Session(self._engine) as session:
            row = session.scalars(select(EntityRow).where(EntityRow.is_self)).first()
            return _to_entity(row) if row else None

    def _find_entities(self, query: str, kind: str | None, limit: int) -> list[Entity]:
        stmt = select(EntityRow).where(EntityRow.search_text.like(f"%{query.lower()}%"))
        if kind is not None:
            stmt = stmt.where(EntityRow.kind == kind)
        with Session(self._engine) as session:
            rows = list(session.scalars(stmt.limit(limit)))
        return [_to_entity(row) for row in rows]

    def _update_entity(
        self, entity_id: int, display_name: str | None, notes: str | None, is_self: bool | None
    ) -> Entity:
        with Session(self._engine) as session:
            row = session.get(EntityRow, entity_id)
            if row is None:
                raise KeyError(entity_id)
            if display_name is not None:
                row.display_name = display_name
            if notes is not None:
                row.notes = notes
            if is_self is not None:
                row.is_self = is_self
            row.search_text = _search_text(row.display_name, row.notes)
            session.commit()
            session.refresh(row)
            return _to_entity(row)

    def _merge_entities(self, keep_id: int, drop_id: int) -> None:
        with Session(self._engine) as session:
            session.execute(
                update(AnchorRow).where(AnchorRow.entity_id == drop_id).values(entity_id=keep_id)
            )
            session.execute(
                update(EdgeRow).where(EdgeRow.from_id == drop_id).values(from_id=keep_id)
            )
            session.execute(update(EdgeRow).where(EdgeRow.to_id == drop_id).values(to_id=keep_id))
            session.execute(
                update(ObservationRow)
                .where(ObservationRow.entity_id == drop_id)
                .values(entity_id=keep_id)
            )
            session.execute(delete(EntityRow).where(EntityRow.id == drop_id))
            session.commit()

    def _add_anchor(
        self, entity_id: int, system: str, ref_type: str, value: str, label: str
    ) -> Anchor:
        row = AnchorRow(
            entity_id=entity_id, system=system, ref_type=ref_type, value=value, label=label
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_anchor(row)

    def _anchors_for(self, entity_id: int, system: str | None) -> list[Anchor]:
        stmt = select(AnchorRow).where(AnchorRow.entity_id == entity_id)
        if system is not None:
            stmt = stmt.where(AnchorRow.system == system)
        with Session(self._engine) as session:
            rows = list(session.scalars(stmt))
        return [_to_anchor(row) for row in rows]

    def _entity_by_anchor(self, system: str, value: str) -> Entity | None:
        stmt = (
            select(EntityRow)
            .join(AnchorRow, AnchorRow.entity_id == EntityRow.id)
            .where(AnchorRow.system == system, func.lower(AnchorRow.value) == value.lower())
        )
        with Session(self._engine) as session:
            row = session.scalars(stmt).first()
        return _to_entity(row) if row else None

    def _add_edge(self, from_id: int, to_id: int, type: str, role: str, notes: str) -> Edge:
        row = EdgeRow(from_id=from_id, to_id=to_id, type=type, role=role, notes=notes)
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_edge(row)

    def _edges_from(self, entity_id: int, type: str | None) -> list[Edge]:
        stmt = select(EdgeRow).where(EdgeRow.from_id == entity_id)
        if type is not None:
            stmt = stmt.where(EdgeRow.type == type)
        with Session(self._engine) as session:
            rows = list(session.scalars(stmt))
        return [_to_edge(row) for row in rows]

    def _edges_to(self, entity_id: int, type: str | None) -> list[Edge]:
        stmt = select(EdgeRow).where(EdgeRow.to_id == entity_id)
        if type is not None:
            stmt = stmt.where(EdgeRow.type == type)
        with Session(self._engine) as session:
            rows = list(session.scalars(stmt))
        return [_to_edge(row) for row in rows]

    def _add_observation(
        self, entity_id: int, content: str, key: str | None, source: str
    ) -> Observation:
        row = ObservationRow(entity_id=entity_id, content=content, key=key, source=source)
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_observation(row)

    def _observations_for(self, entity_id: int) -> list[Observation]:
        stmt = select(ObservationRow).where(ObservationRow.entity_id == entity_id)
        with Session(self._engine) as session:
            rows = list(session.scalars(stmt))
        return [_to_observation(row) for row in rows]

    def _vocabulary(self) -> dict[str, list[str]]:
        with Session(self._engine) as session:
            return {
                "kind": list(session.scalars(select(EntityRow.kind).distinct())),
                "system": list(session.scalars(select(AnchorRow.system).distinct())),
                "ref_type": list(session.scalars(select(AnchorRow.ref_type).distinct())),
                "relation": list(session.scalars(select(EdgeRow.type).distinct())),
            }

    def _record_interaction(self, entity_id: int, kind: str, at: float) -> None:
        with Session(self._engine) as session:
            session.add(InteractionRow(entity_id=entity_id, kind=kind, at=at))
            session.commit()

    def _interaction_stats(self, entity_id: int) -> InteractionStats:
        stmt = select(func.count(InteractionRow.id), func.max(InteractionRow.at)).where(
            InteractionRow.entity_id == entity_id
        )
        with Session(self._engine) as session:
            count, last_at = session.execute(stmt).one()
        return InteractionStats(count=count, last_at=last_at)


def _to_entity(row: EntityRow) -> Entity:
    return Entity(
        id=row.id,
        kind=row.kind,
        display_name=row.display_name,
        is_self=row.is_self,
        notes=row.notes,
    )


def _to_anchor(row: AnchorRow) -> Anchor:
    return Anchor(
        id=row.id,
        entity_id=row.entity_id,
        system=row.system,
        ref_type=row.ref_type,
        value=row.value,
        label=row.label,
    )


def _to_edge(row: EdgeRow) -> Edge:
    return Edge(
        id=row.id,
        from_id=row.from_id,
        to_id=row.to_id,
        type=row.type,
        role=row.role,
        notes=row.notes,
    )


def _to_observation(row: ObservationRow) -> Observation:
    return Observation(
        id=row.id,
        entity_id=row.entity_id,
        content=row.content,
        key=row.key,
        source=row.source,
    )
