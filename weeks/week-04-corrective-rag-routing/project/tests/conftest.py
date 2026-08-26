"""Shared fixtures. Tests that need the pgvector store use the `pg_store` fixture,
which skips cleanly (rather than erroring) if Postgres isn't reachable -- run
`docker compose up -d` in project/ first."""

import pytest

from app.data import seed_demo_data
from app.vectorstore import PGVectorStore, is_available

POSTGRES_UP = is_available()

requires_postgres = pytest.mark.skipif(
    not POSTGRES_UP,
    reason="Postgres/pgvector not reachable at DATABASE_URL -- run `docker compose up -d` first",
)


@pytest.fixture(scope="session")
def pg_store():
    if not POSTGRES_UP:
        pytest.skip("Postgres/pgvector not reachable at DATABASE_URL -- run `docker compose up -d` first")
    store = PGVectorStore()
    store.clear()
    seed_demo_data(store)
    yield store
    store.close()
