import pytest

from app import db, ingest


@pytest.fixture(scope="session")
def seeded_database():
    """Only requested by tests that need a live ParadeDB instance -- test_fusion.py
    is a pure function and must never be skipped just because Postgres is down."""
    try:
        conn = db.get_connection()
        conn.close()
    except Exception as exc:  # noqa: BLE001 - any connection failure means "skip"
        pytest.skip(f"Postgres (ParadeDB) not reachable at DATABASE_URL: {exc}")
    ingest.run()


@pytest.fixture(scope="module")
def conn(seeded_database):
    connection = db.get_connection()
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def title_to_id(conn):
    return dict(conn.execute("SELECT title, id FROM documents").fetchall())
