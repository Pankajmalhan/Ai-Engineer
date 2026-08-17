from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from app.config import DATABASE_URL

SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()


def get_connection() -> psycopg.Connection:
    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    register_vector(conn)
    return conn


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_SQL)


def insert_documents(
    conn: psycopg.Connection, rows: list[tuple[str, str, list[float]]]
) -> None:
    """rows: list of (title, content, embedding)."""
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO documents (title, content, embedding) VALUES (%s, %s, %s)",
            rows,
        )


def dense_search(
    conn: psycopg.Connection, query_embedding: list[float], limit: int
) -> list[tuple[int, str, str, float]]:
    """Returns (id, title, content, cosine_distance) ordered nearest-first."""
    rows = conn.execute(
        """
        SELECT id, title, content, embedding <=> %s::vector AS distance
        FROM documents
        ORDER BY distance
        LIMIT %s
        """,
        (query_embedding, limit),
    ).fetchall()
    return rows


def sparse_search(
    conn: psycopg.Connection, query_text: str, limit: int
) -> list[tuple[int, str, str, float]]:
    """Returns (id, title, content, bm25_score) ordered highest-score-first.

    Uses pg_search's ||| match-disjunction operator (OR across the query's
    tokens) against the BM25 index built in schema.sql, and paradedb.score()
    to expose the underlying BM25 score. ||| tokenizes the right-hand side
    as plain text rather than parsing it as a query-string DSL, so raw user
    input containing apostrophes/colons/etc. (like "won't") doesn't blow up
    a query parser the way the @@@ operator's DSL would.
    """
    rows = conn.execute(
        """
        SELECT id, title, content, paradedb.score(id) AS score
        FROM documents
        WHERE content ||| %s
        ORDER BY score DESC
        LIMIT %s
        """,
        (query_text, limit),
    ).fetchall()
    return rows
