from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from otwarta.storage.models import Base


def init_db(database_url: str = "sqlite:///./data/raw/otwarta.db") -> Engine:
    connect_args = {"check_same_thread": False} if "sqlite" in database_url else {}
    engine = create_engine(database_url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def get_session(engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(engine)
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
