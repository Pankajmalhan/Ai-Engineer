"""Ingest the benchmark corpus: embed every document once, load into
Postgres. Identical to Week 1's ingest.py, pointed at this week's own
ParadeDB container (see config.py / docker-compose.yml)."""

from app import db
from app.corpus import DOCUMENTS
from app.embeddings import embed_passages


def run() -> None:
    conn = db.get_connection()
    db.init_schema(conn)

    titles = [title for title, _ in DOCUMENTS]
    contents = [content for _, content in DOCUMENTS]
    vectors = embed_passages(contents)

    rows = list(zip(titles, contents, vectors))
    db.insert_documents(conn, rows)

    count = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
    print(f"Ingested {count} documents.")


if __name__ == "__main__":
    run()
