from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from otwarta.storage.models import Base


def _apply_schema_migrations(engine: Engine) -> None:
    """Add new columns to existing tables that predate model changes."""
    new_columns = [
        ("analysis_results", "hateful_score", "FLOAT"),
        ("analysis_results", "secondary_model_id", "VARCHAR"),
        ("analysis_results", "secondary_model_score", "FLOAT"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in new_columns:
            existing = {
                row[1]
                for row in conn.execute(
                    text(f"PRAGMA table_info({table})")
                )
            }
            if column not in existing:
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                    )
                )
        conn.commit()


def init_db(database_url: str = "sqlite:///./data/raw/otwarta.db") -> Engine:
    connect_args = {"check_same_thread": False, "timeout": 30} if "sqlite" in database_url else {}
    engine = create_engine(database_url, connect_args=connect_args)

    if "sqlite" in database_url:
        @event.listens_for(engine, "connect")
        def set_wal_mode(dbapi_conn: Any, _: Any) -> None:
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA synchronous=NORMAL")
    Base.metadata.create_all(engine)
    _apply_schema_migrations(engine)
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
