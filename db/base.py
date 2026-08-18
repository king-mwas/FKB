"""
SQLAlchemy engine/session setup. Postgres (Supabase) when DATABASE_URL is
set -- lets the live_engine process (writer) and the webapp process
(reader, occasional writer) share one remote database, browsable directly
in Supabase's own table editor instead of only through this app. Falls
back to local SQLite (WAL mode) when DATABASE_URL isn't set yet, so the
app keeps working before Supabase is wired up.
"""

import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Load .env here (not only in live_engine/config.py) so every entry point
# that touches the DB -- the webapp, scripts/init_db.py, ad-hoc scripts --
# picks up DATABASE_URL, not just the live engine. Without this, running
# init_db.py or the webapp would silently ignore a DATABASE_URL set only in
# .env and fall back to SQLite.
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_PATH = os.environ.get("FKB_DB_PATH", "./data/fkb.db")

if DATABASE_URL:
    # pool_pre_ping: a remote connection (unlike a local SQLite file) can go
    # stale between polls -- network blip, Supabase's pooler idling it out
    # -- so check liveness before handing a connection to a query.
    engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
else:
    engine = create_engine(f"sqlite:///{DB_PATH}", future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    """FastAPI dependency: yields a session, commits on success, rolls back
    on exception. Distinct from get_session() (a plain context manager for
    use in scripts/the live engine) only in calling convention."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create all tables that don't already exist. Non-destructive."""
    import db.models  # noqa: F401  (registers models on Base.metadata)
    if not DATABASE_URL:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    Base.metadata.create_all(engine)
