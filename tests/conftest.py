"""Shared test fixtures — uses an in-memory SQLite database for fast isolated tests."""

import os
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

# Override DATABASE_URL before importing cloudledger modules
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ALLOWED_ORIGINS"] = "*"

from cloudledger.database import Base  # noqa: E402


@pytest.fixture(autouse=True)
def db_session(monkeypatch):
    """Create a fresh in-memory SQLite database for each test.

    Uses shared cache so the same in-memory db is accessible from multiple threads
    (needed for FastAPI TestClient which runs endpoints in a thread pool).
    """
    engine = create_engine(
        "sqlite:///file::memory:?cache=shared&uri=true",
        echo=False,
        connect_args={"check_same_thread": False},
    )

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

    # Patch get_db in every module that imports it
    import cloudledger.database
    import cloudledger.ingest
    import cloudledger.normalize
    import cloudledger.variance
    import cloudledger.quality
    import cloudledger.allocate
    import cloudledger.anomaly
    import backend.server as server_mod

    monkeypatch.setattr(cloudledger.database, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.ingest, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.normalize, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.variance, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.quality, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.allocate, "get_db", _get_db)
    monkeypatch.setattr(cloudledger.anomaly, "get_db", _get_db)
    # backend.server.get_db() delegates to cloudledger.database.get_db,
    # but we patch it directly so TestClient threads use the right session
    monkeypatch.setattr(server_mod, "get_db", _get_db)

    yield _get_db

    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session, monkeypatch):
    """FastAPI TestClient with patched database and a pre-authenticated user.

    Provides a test client with a valid JWT in the Authorization header.
    """
    import cloudledger.database
    import backend.server as server_mod
    from backend.server import app
    from backend.auth import create_token
    from cloudledger.database import User

    # Prevent lifespan from calling create_all_tables (already done by db_session)
    monkeypatch.setattr(cloudledger.database, "create_all_tables", lambda: None)
    monkeypatch.setattr(server_mod, "create_all_tables", lambda: None)

    # Seed a test user
    from backend.auth import hash_password
    with db_session() as session:
        user = User(email="test@example.com", password_hash=hash_password("testpass123"), name="Test")
        session.add(user)
        session.flush()
        uid = user.id

    token = create_token(uid, "test@example.com")

    from fastapi.testclient import TestClient
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as tc:
        yield tc
