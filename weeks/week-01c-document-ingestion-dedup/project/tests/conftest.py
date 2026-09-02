"""Shared fixtures/markers.

- `requires_postgres`: skips cleanly if Postgres/pgvector isn't reachable at
  DATABASE_URL (run `docker compose up -d` in project/ first).
- `requires_ocr`: skips cleanly if tesseract/poppler aren't on PATH (scanned-PDF
  OCR tests only -- digital-text PDF loading doesn't need them).
- `requires_presidio`: skips cleanly if the spaCy model Presidio needs hasn't been
  downloaded (`uv run python -m spacy download en_core_web_sm`).

Real .docx/.pdf fixtures are generated once into tests/fixtures/ (sample.md and
sample.html are checked in directly).
"""

import pytest

from app.loaders import ocr_available
from app.pii import presidio_available
from app.vectorstore import PGVectorStore, is_available
from tests.generate_fixtures import ensure_fixtures

ensure_fixtures()

POSTGRES_UP = is_available()
OCR_UP = ocr_available()
PRESIDIO_UP = presidio_available()

requires_postgres = pytest.mark.skipif(
    not POSTGRES_UP,
    reason="Postgres/pgvector not reachable at DATABASE_URL -- run `docker compose up -d` first",
)
requires_ocr = pytest.mark.skipif(
    not OCR_UP,
    reason="tesseract/poppler not on PATH -- scanned-PDF OCR needs both installed",
)
requires_presidio = pytest.mark.skipif(
    not PRESIDIO_UP,
    reason="en_core_web_sm not downloaded -- run `uv run python -m spacy download en_core_web_sm`",
)


@pytest.fixture
def pg_store():
    if not POSTGRES_UP:
        pytest.skip("Postgres/pgvector not reachable at DATABASE_URL -- run `docker compose up -d` first")
    store = PGVectorStore()
    store.clear()
    yield store
    store.clear()
    store.close()
