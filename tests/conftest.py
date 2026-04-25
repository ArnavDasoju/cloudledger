"""Shared test fixtures — uses an in-memory SQLite database for fast isolated tests."""

import os
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

# Override DATABASE_URL before importing cloudledger modules
os.environ["DATABASE_URL"] = "sqlite://"

from cloudledger.database import Base  # noqa: E402


@pytest.fixture(autouse=True)
def db_session(monkeypatch):
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite://", echo=False, native_datetime=True)

    # Tell SQLite to accept date strings without conversion errors
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    @contextmanager
    def _get_db():
        session = TestSession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # Patch get_db everywhere it's used
    import cloudledger.ingest
    import cloudledger.normalize
    import cloudledger.variance
    import cloudledger.quality
    import cloudledger.allocate
    import cloudledger.anomaly
    monkeypatch.setattr(cloudledger.ingest, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.normalize, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.variance, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.quality, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.allocate, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.anomaly, "get_db", _get_db)

    yield _get_db

    Base.metadata.drop_all(engine)
