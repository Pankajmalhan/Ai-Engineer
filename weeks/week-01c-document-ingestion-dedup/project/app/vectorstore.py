"""pgvector-backed document store with a `content_hash` column: incremental upsert
only re-embeds and re-writes rows whose hash actually changed since the last run,
instead of blindly re-embedding the whole corpus on every ingest.

`skipped_documents` records the hash of every document IngestionPipeline decided to
drop as a near-duplicate, keyed by id but with no embedding. Without this, a
dropped-duplicate id has no row in `documents` at all, so a naive "is this id's hash
already stored" check would call it changed on *every* subsequent run (it never
matches), sending it back through redaction and dedup indefinitely -- and, since
dedup only compares within the current run's batch, it could slip into `documents` as
a false-unique on some later run where its original near-dup source isn't part of the
batch. Recording the skip decision here makes it durable across runs, the same way an
upsert is.
"""

from __future__ import annotations

import time

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from app.config import DATABASE_URL
from app.embeddings import EMBEDDING_DIM, embed
from app.models import ProcessedDocument, UpsertStats


def is_available(database_url: str | None = None) -> bool:
    try:
        with psycopg.connect(database_url or DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


class PGVectorStore:
    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or DATABASE_URL
        self._conn = psycopg.connect(self.database_url, autocommit=True)
        self._ensure_schema()
        register_vector(self._conn)

    def _ensure_schema(self) -> None:
        self._conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                embedding vector({EMBEDDING_DIM}) NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skipped_documents (
                id TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL
            )
            """
        )

    def existing_hashes(self, ids: list[str]) -> dict[str, str]:
        """Hash of the last-processed version of each id, whether it ended up
        indexed (`documents`) or dropped as a near-duplicate (`skipped_documents`)
        -- an id is in at most one of the two tables at a time."""
        if not ids:
            return {}
        rows = self._conn.execute(
            """
            SELECT id, content_hash FROM documents WHERE id = ANY(%s)
            UNION ALL
            SELECT id, content_hash FROM skipped_documents WHERE id = ANY(%s)
            """,
            (ids, ids),
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def incremental_upsert(self, documents: list[ProcessedDocument]) -> UpsertStats:
        """Only upserts documents whose content_hash differs from the stored value
        (new documents count as changed -- no stored hash to match). Unchanged
        documents are skipped entirely: no re-embed, no write."""
        start = time.perf_counter()
        if not documents:
            return UpsertStats(upserted=0, skipped=0, elapsed_seconds=time.perf_counter() - start)

        existing = self.existing_hashes([d.id for d in documents])
        changed = [d for d in documents if existing.get(d.id) != d.hash]
        skipped = len(documents) - len(changed)

        if changed:
            vectors = embed([d.text for d in changed])
            with self._conn.cursor() as cur:
                for doc, vec in zip(changed, vectors):
                    cur.execute("DELETE FROM skipped_documents WHERE id = %s", (doc.id,))
                    cur.execute(
                        """
                        INSERT INTO documents (id, content, content_hash, embedding)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE
                            SET content = EXCLUDED.content,
                                content_hash = EXCLUDED.content_hash,
                                embedding = EXCLUDED.embedding
                        """,
                        (doc.id, doc.text, doc.hash, Vector(vec)),
                    )

        return UpsertStats(upserted=len(changed), skipped=skipped, elapsed_seconds=time.perf_counter() - start)

    def mark_skipped(self, dropped: list[tuple[str, str]]) -> None:
        """Records (id, content_hash) pairs for documents dropped as near-duplicates
        this run, so a future run with the same raw content recognizes the id as
        already-decided instead of treating it as new/changed."""
        if not dropped:
            return
        with self._conn.cursor() as cur:
            for doc_id, doc_hash in dropped:
                cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
                cur.execute(
                    """
                    INSERT INTO skipped_documents (id, content_hash)
                    VALUES (%s, %s)
                    ON CONFLICT (id) DO UPDATE SET content_hash = EXCLUDED.content_hash
                    """,
                    (doc_id, doc_hash),
                )

    def all_ids(self) -> list[str]:
        rows = self._conn.execute("SELECT id FROM documents").fetchall()
        return [row[0] for row in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT count(*) FROM documents").fetchone()[0]

    def clear(self) -> None:
        self._conn.execute("DELETE FROM documents")
        self._conn.execute("DELETE FROM skipped_documents")

    def close(self) -> None:
        self._conn.close()
