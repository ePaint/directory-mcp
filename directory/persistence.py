"""Shared SQLAlchemy declarative base for all directory tables."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
