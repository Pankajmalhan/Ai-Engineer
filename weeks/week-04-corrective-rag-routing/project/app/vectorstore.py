"""A small pgvector-backed document store.

One `chunks` table, partitioned by a `collection` column so the FACTUAL and CODE
routes can live in the same Postgres instance as separate collections (e.g. "docs" vs
"code") without separate schemas. `docker-compose.yml` in this directory runs the
Postgres + pgvector image this connects to by default; `DATABASE_URL` overrides it.
"""

from __future__ import annotations

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from app.config import DATABASE_URL
from app.embeddings import EMBEDDING_DIM, embed, embed_one
from app.models import Document, RetrievedChunk


def is_available(database_url: str | None = None) -> bool:
    """Best-effort connectivity check, used by tests to skip cleanly when the
    docker-compose Postgres isn't running rather than failing with a connection error."""
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
            CREATE TABLE IF NOT EXISTS chunks (
                collection TEXT NOT NULL,
                id TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding vector({EMBEDDING_DIM}) NOT NULL,
                PRIMARY KEY (collection, id)
            )
            """
        )

    def upsert(self, collection: str, documents: list[Document]) -> None:
        if not documents:
            return
        vectors = embed([d.text for d in documents])
        with self._conn.cursor() as cur:
            for doc, vec in zip(documents, vectors):
                cur.execute(
                    """
                    INSERT INTO chunks (collection, id, content, embedding)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (collection, id) DO UPDATE
                        SET content = EXCLUDED.content, embedding = EXCLUDED.embedding
                    """,
                    (collection, doc.id, doc.text, Vector(vec)),
                )

    def similarity_search(self, collection: str, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        query_vec = Vector(embed_one(query))
        rows = self._conn.execute(
            """
            SELECT id, content, 1 - (embedding <=> %s) AS score
            FROM chunks
            WHERE collection = %s
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (query_vec, collection, query_vec, top_k),
        ).fetchall()
        return [RetrievedChunk(id=row[0], text=row[1], score=float(row[2])) for row in rows]

    def all_documents(self, collection: str) -> list[Document]:
        rows = self._conn.execute(
            "SELECT id, content FROM chunks WHERE collection = %s", (collection,)
        ).fetchall()
        return [Document(id=row[0], text=row[1]) for row in rows]

    def clear(self, collection: str | None = None) -> None:
        if collection is not None:
            self._conn.execute("DELETE FROM chunks WHERE collection = %s", (collection,))
        else:
            self._conn.execute("DELETE FROM chunks")

    def close(self) -> None:
        self._conn.close()
