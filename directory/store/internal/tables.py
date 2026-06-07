"""SQLAlchemy tables for the directory graph — registered on the shared Base."""

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from directory.persistence import Base


class EntityRow(Base):
    __tablename__ = "entity"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(index=True)
    display_name: Mapped[str]
    search_text: Mapped[str] = mapped_column(index=True)
    is_self: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str] = mapped_column(default="")


class AnchorRow(Base):
    __tablename__ = "anchor"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    system: Mapped[str]
    ref_type: Mapped[str]
    value: Mapped[str]
    label: Mapped[str] = mapped_column(default="")

    __table_args__ = (Index("ix_anchor_system_value", "system", "value"),)


class EdgeRow(Base):
    __tablename__ = "edge"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    to_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    type: Mapped[str]
    role: Mapped[str] = mapped_column(default="")
    notes: Mapped[str] = mapped_column(default="")


class ObservationRow(Base):
    __tablename__ = "observation"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    content: Mapped[str]
    key: Mapped[str | None] = mapped_column(default=None)
    source: Mapped[str] = mapped_column(default="")


class InteractionRow(Base):
    __tablename__ = "interaction"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    kind: Mapped[str]
    at: Mapped[float]
