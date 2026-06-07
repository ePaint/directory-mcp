from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from directory.persistence import Base


def sql_engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine
